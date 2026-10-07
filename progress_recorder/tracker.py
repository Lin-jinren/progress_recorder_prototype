from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .database import Database
from .idle import get_idle_seconds


@dataclass(frozen=True)
class ActiveWindow:
    app_name: str
    title: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.app_name, self.title)


def get_active_window() -> Optional[ActiveWindow]:
    """Return the current foreground window, or None when the OS blocks access."""
    try:
        import pywinctl as pwc

        window = pwc.getActiveWindow()
        if window is None:
            return None

        title = (getattr(window, "title", "") or "").strip()
        app_name = "Unknown app"

        try:
            import psutil

            pid = window.getPID()
            if pid:
                app_name = psutil.Process(pid).name()
        except Exception:
            # Window title is still useful even if process lookup is unavailable.
            pass

        return ActiveWindow(app_name=app_name, title=title)
    except Exception:
        # Typical examples: Linux Wayland restrictions, missing permissions on macOS,
        # or no graphical desktop in the current session.
        return None


class ActivityTracker:
    """Turns periodic samples into window sessions and idle periods.

    - A window session lasts while the same (app, title) stays in front.
    - No keyboard/mouse input for `idle_threshold` seconds ends the session at the
      last input time and opens an idle period instead.
    - Anything that interrupts sampling (unreadable window, the recorder itself in
      front, or a long gap such as sleep/hibernate) ends the session, so time we
      did not observe is never added to a session.
    """

    def __init__(
        self,
        db: Database,
        *,
        idle_threshold: float = 300,
        poll_seconds: float = 5,
        window_provider: Callable[[], Optional[ActiveWindow]] = get_active_window,
        idle_provider: Callable[[], Optional[float]] = get_idle_seconds,
        clock: Callable[[], float] = time.time,
    ):
        self.db = db
        self.idle_threshold = idle_threshold
        self.max_gap = max(poll_seconds * 3, 30)
        self.window_provider = window_provider
        self.idle_provider = idle_provider
        self.clock = clock

        self.current: Optional[ActiveWindow] = None
        self.current_event_id: Optional[int] = None
        self.idle_event_id: Optional[int] = None
        self.last_sample_at: Optional[float] = None
        # Nothing new may start before this time (end of the last unobserved gap).
        self._floor = 0.0
        self.last_error = ""

    def sample(self) -> str:
        now = self.clock()
        idle = self.idle_provider()
        last_input = None if idle is None else now - idle

        if self.last_sample_at is not None and now - self.last_sample_at > self.max_gap:
            # Sleep / hibernate / frozen app: close everything at the last moment we
            # actually saw, and never count the gap.
            gap_start = self.last_sample_at
            self.stop_current(ended_at=gap_start)
            self._floor = gap_start
        self.last_sample_at = now

        if last_input is not None and idle >= self.idle_threshold:
            self._close_window(ended_at=last_input)
            if self.idle_event_id is None:
                self.idle_event_id = self.db.add_event(
                    "idle", started_at=max(last_input, self._floor), ended_at=now
                )
            else:
                self.db.extend_event(self.idle_event_id, now)
            return "idle"

        self._close_idle(ended_at=now if last_input is None else last_input)

        active = self.window_provider()
        if active is None:
            self._close_window(ended_at=now)
            self.last_error = "無法讀取前景視窗（Wayland / macOS 權限 / 無桌面環境時可能發生）"
            return "unavailable"

        if self._is_recorder_itself(active):
            self._close_window(ended_at=now)
            return "ignored"

        self.last_error = ""
        if self.current is None or active.key != self.current.key:
            self._close_window(ended_at=now)
            self.current = active
            self.current_event_id = self.db.add_event(
                "window",
                app_name=active.app_name,
                title=active.title,
                started_at=now,
                ended_at=now,
            )
            return "changed"

        self.db.extend_event(self.current_event_id, now)
        return "same"

    def stop_current(self, ended_at: Optional[float] = None) -> None:
        end = self.clock() if ended_at is None else ended_at
        self._close_window(ended_at=end)
        self._close_idle(ended_at=end)
        self.last_sample_at = None

    def _close_window(self, ended_at: float) -> None:
        if self.current_event_id is not None:
            self.db.extend_event(self.current_event_id, ended_at)
        self.current = None
        self.current_event_id = None

    def _close_idle(self, ended_at: float) -> None:
        if self.idle_event_id is not None:
            self.db.extend_event(self.idle_event_id, ended_at)
        self.idle_event_id = None

    @staticmethod
    def _is_recorder_itself(active: ActiveWindow) -> bool:
        own_process = os.path.basename(
            os.getenv("PROGRESS_RECORDER_PROCESS", "progressrecorder")
        ).lower()
        return "progress recorder" in active.title.lower() or own_process in active.app_name.lower()

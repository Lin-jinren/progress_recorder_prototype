from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .database import Database


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

        if not title and not app_name:
            return None
        return ActiveWindow(app_name=app_name, title=title)
    except Exception:
        # Typical examples: Linux Wayland restrictions, missing permissions on macOS,
        # or no graphical desktop in the current session.
        return None


class ActivityTracker:
    """Creates one DB session per active-window period."""

    def __init__(self, db: Database):
        self.db = db
        self.current: Optional[ActiveWindow] = None
        self.current_event_id: Optional[int] = None
        self.last_error = ""

    def sample(self) -> str:
        active = get_active_window()
        if active is None:
            self.last_error = "無法讀取前景視窗（Wayland / macOS 權限 / 無桌面環境時可能發生）"
            return "unavailable"

        # Do not record the recorder itself.
        own_process = os.path.basename(os.getenv("PROGRESS_RECORDER_PROCESS", "progressrecorder")).lower()
        if "progress recorder" in active.title.lower() or own_process in active.app_name.lower():
            return "ignored"

        self.last_error = ""
        if self.current is None or active.key != self.current.key:
            self.stop_current()
            self.current = active
            self.current_event_id = self.db.add_event(
                "window",
                app_name=active.app_name,
                title=active.title,
            )
            return "changed"

        if self.current_event_id is not None:
            self.db.extend_event(self.current_event_id)
        return "same"

    def stop_current(self) -> None:
        if self.current_event_id is not None:
            self.db.extend_event(self.current_event_id)
        self.current = None
        self.current_event_id = None

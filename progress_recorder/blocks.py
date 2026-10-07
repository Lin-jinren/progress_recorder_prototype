"""Group a day's work events into blocks the user can review.

A block is a stretch of work; a gap of BREAK_SECONDS without any work event
(lunch, a video, idle, unclassified browsing...) starts a new block. This module
has no Qt dependency so it can be tested and reused by any output (md / Notion / pptx).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .classifier import UNKNOWN, WORK, clean_title, is_browser
from .database import Event

BREAK_SECONDS = 10 * 60
MIN_BLOCK_WORK_SECONDS = 60
MIN_UNKNOWN_SECONDS = 30


@dataclass
class WorkBlock:
    start: float
    end: float
    work_seconds: float = 0.0
    app_seconds: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    title_seconds: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    file_counts: Counter = field(default_factory=Counter)
    notes: list[str] = field(default_factory=list)

    def top_apps(self, n: int = 3) -> list[tuple[str, float]]:
        return sorted(self.app_seconds.items(), key=lambda item: item[1], reverse=True)[:n]

    def top_titles(self, n: int = 5) -> list[str]:
        ranked = sorted(self.title_seconds.items(), key=lambda item: item[1], reverse=True)
        return [title for title, secs in ranked[:n] if secs >= 30]

    def top_files(self, n: int = 5) -> list[tuple[str, int]]:
        return [(Path(path).name, count) for path, count in self.file_counts.most_common(n)]


@dataclass
class UnknownItem:
    """Unclassified activity grouped the way a rule would match it."""

    field: str  # "app" for normal programs, "title" for browser pages
    value: str  # suggested text for the rule
    app_name: str
    seconds: float


def _clip(event: Event, day_start: float, day_end: float) -> tuple[float, float]:
    return max(event.started_at, day_start), min(event.ended_at, day_end)


def build_blocks(
    events: list[Event], categories: dict[int, str], day_start: float, day_end: float
) -> list[WorkBlock]:
    blocks: list[WorkBlock] = []
    current: WorkBlock | None = None

    for event in sorted(events, key=lambda e: e.started_at):
        if categories.get(event.id) != WORK:
            continue
        start, end = _clip(event, day_start, day_end)
        if end < start:
            continue
        if current is None or start - current.end > BREAK_SECONDS:
            current = WorkBlock(start=start, end=end)
            blocks.append(current)
        current.end = max(current.end, end)

        if event.event_type == "window":
            seconds = end - start
            current.work_seconds += seconds
            current.app_seconds[event.app_name or "Unknown app"] += seconds
            title = clean_title(event.title)
            if title:
                current.title_seconds[title] += seconds
        elif event.event_type == "file" and event.file_path:
            current.file_counts[event.file_path] += 1
        elif event.event_type == "note" and event.detail.strip():
            current.notes.append(event.detail.strip())

    # A lone file save (e.g. cloud sync) is not a work block; a note always is.
    return [b for b in blocks if b.work_seconds >= MIN_BLOCK_WORK_SECONDS or b.notes]


def unknown_items(
    events: list[Event], categories: dict[int, str], day_start: float, day_end: float
) -> list[UnknownItem]:
    """Unclassified windows, grouped by program (or by page for browsers), longest first."""
    totals: dict[tuple[str, str], float] = defaultdict(float)
    apps: dict[tuple[str, str], str] = {}

    for event in events:
        if event.event_type != "window" or categories.get(event.id) != UNKNOWN:
            continue
        start, end = _clip(event, day_start, day_end)
        if is_browser(event.app_name):
            key = ("title", clean_title(event.title))
        else:
            key = ("app", event.app_name)
        totals[key] += max(0.0, end - start)
        apps[key] = event.app_name

    items = [
        UnknownItem(field=f, value=v, app_name=apps[(f, v)], seconds=secs)
        for (f, v), secs in totals.items()
        if secs >= MIN_UNKNOWN_SECONDS
    ]
    return sorted(items, key=lambda item: item.seconds, reverse=True)

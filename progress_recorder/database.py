from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Iterator, Optional


@dataclass
class Event:
    id: int
    event_type: str  # "window" | "file" | "note" | "idle"
    started_at: float
    ended_at: float
    app_name: str
    title: str
    detail: str
    file_path: str

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.ended_at - self.started_at)


def day_bounds(target: date) -> tuple[float, float]:
    """Local-time [start, end) timestamps of a day. Naive datetimes follow DST correctly."""
    start = datetime.combine(target, dt_time.min).timestamp()
    end = datetime.combine(target + timedelta(days=1), dt_time.min).timestamp()
    return start, end


class Database:
    """Very small SQLite wrapper; intentionally no ORM to keep it easy to edit."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # sqlite3's own `with conn:` only commits; it never closes the connection,
        # which leaves the DB file locked on Windows. Always close here.
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL NOT NULL,
                    app_name TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',
                    file_path TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_started_at ON events(started_at)"
            )

    def add_event(
        self,
        event_type: str,
        *,
        app_name: str = "",
        title: str = "",
        detail: str = "",
        file_path: str = "",
        started_at: Optional[float] = None,
        ended_at: Optional[float] = None,
    ) -> int:
        start = time.time() if started_at is None else started_at
        end = start if ended_at is None else ended_at
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO events
                    (event_type, started_at, ended_at, app_name, title, detail, file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_type, start, end, app_name, title, detail, file_path),
            )
            return int(cur.lastrowid)

    def extend_event(self, event_id: int, ended_at: Optional[float] = None) -> None:
        """Set an event's end time. Never moves the end before the start."""
        end = time.time() if ended_at is None else ended_at
        with self._connect() as conn:
            conn.execute(
                "UPDATE events SET ended_at = MAX(started_at, ?) WHERE id = ?",
                (end, event_id),
            )

    def events_for_day(self, target: date) -> list[Event]:
        """All events overlapping the day, including sessions that cross midnight."""
        start, end = day_bounds(target)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE started_at < ? AND ended_at >= ?
                ORDER BY started_at ASC
                """,
                (end, start),
            ).fetchall()
        return [Event(**dict(row)) for row in rows]

    def latest_events(self, limit: int = 100) -> list[Event]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Event(**dict(row)) for row in rows]

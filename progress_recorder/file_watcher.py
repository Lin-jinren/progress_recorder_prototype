from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Iterable

from .database import Database


class FileWatcher:
    """Watch selected folders and log meaningful file changes."""

    def __init__(self, db: Database, extensions: Iterable[str]):
        self.db = db
        self.extensions = {ext.lower() for ext in extensions}
        self._observer = None
        self._recent: dict[str, float] = {}
        self._lock = Lock()

    def start(self, folders: Iterable[str]) -> None:
        self.stop()
        valid = [Path(folder).expanduser() for folder in folders if Path(folder).expanduser().is_dir()]
        if not valid:
            return

        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            return

        watcher = self

        class Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if not event.is_directory:
                    watcher._record("modified", event.src_path)

            def on_created(self, event):
                if not event.is_directory:
                    watcher._record("created", event.src_path)

            def on_moved(self, event):
                if not event.is_directory:
                    watcher._record("moved", event.dest_path)

        observer = Observer()
        handler = Handler()
        for folder in valid:
            observer.schedule(handler, str(folder), recursive=True)
        observer.daemon = True
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None

    def _record(self, action: str, raw_path: str) -> None:
        path = Path(raw_path)
        name = path.name
        if name.startswith("~$") or name.startswith("."):
            return
        if self.extensions and path.suffix.lower() not in self.extensions:
            return

        # Office programs and editors can emit many duplicate events for one save.
        now = time.time()
        key = str(path.resolve())
        with self._lock:
            last = self._recent.get(key, 0)
            if now - last < 3:
                return
            self._recent[key] = now
            if len(self._recent) > 1000:
                self._recent = {k: t for k, t in self._recent.items() if now - t < 3}

        self.db.add_event(
            "file",
            detail=action,
            file_path=key,
            title=name,
        )

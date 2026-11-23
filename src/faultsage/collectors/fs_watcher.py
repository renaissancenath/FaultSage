"""File watcher (FR-9) using watchdog. Reports saves under the root except ignored paths."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from faultsage.collectors.spool import SpoolWriter
from faultsage.paths import is_ignored, to_posix_rel


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


class FsWatcher:
    def __init__(
        self, root: Path, writer: SpoolWriter, on_change: Callable[[], None] | None = None
    ) -> None:
        self.root = root
        self.writer = writer
        self.on_change = on_change
        self._observer: Any = None

    def start(self) -> None:
        from watchdog.events import FileSystemEvent, FileSystemEventHandler
        from watchdog.observers import Observer

        outer = self

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event: FileSystemEvent) -> None:
                if event.is_directory:
                    return
                src = str(event.src_path)
                rel = to_posix_rel(outer.root, src)
                if rel.startswith(".faultsage/spool"):
                    if outer.on_change:
                        outer.on_change()
                    return
                if is_ignored(rel) or not rel.endswith(".py"):
                    return
                change = {
                    "created": "created",
                    "modified": "modified",
                    "deleted": "deleted",
                    "moved": "moved",
                }.get(event.event_type)
                if change is None:
                    return
                outer.writer.write(
                    "file_change",
                    {
                        "file_path": rel,
                        "change": change,
                        "sha256": None if change == "deleted" else _sha(Path(src)),
                    },
                )

        self._observer = Observer()
        self._observer.schedule(_Handler(), str(self.root), recursive=True)
        self._observer.daemon = True
        self._observer.start()

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)

"""Append-only JSONL spool writer (FR-6, D-005). Collectors only write here."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from faultsage import __version__
from faultsage.models.events import Event
from faultsage.paths import secure_mkdir
from faultsage.redact import redact_obj

ROTATE_BYTES = 10 * 1024 * 1024


class SpoolWriter:
    """One writer per process. Each process writes its own files so writers never interleave."""

    def __init__(self, spool_dir: Path, collector: str, project_root: Path) -> None:
        self.dir = secure_mkdir(spool_dir)
        self.collector = collector
        self.project_root = project_root.resolve().as_posix()
        self._n = 0
        self._lock = threading.Lock()
        self._path = self._next_path()

    def _next_path(self) -> Path:
        while True:
            p = self.dir / f"{self.collector}-{os.getpid()}-{self._n}.jsonl"
            if not p.exists() or p.stat().st_size < ROTATE_BYTES:
                return p
            self._n += 1

    def write(self, kind: str, body: dict[str, Any]) -> Event:
        event = Event(
            kind=kind,  # type: ignore[arg-type]
            project_root=self.project_root,
            collector=self.collector,
            collector_version=__version__,
            body=redact_obj(body),  # type: ignore[arg-type]
        )
        line = event.to_json() + "\n"
        with self._lock:
            if self._path.exists() and self._path.stat().st_size >= ROTATE_BYTES:
                self._n += 1
                self._path = self._next_path()
            # Single write call with O_APPEND keeps lines whole.
            fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
        return event

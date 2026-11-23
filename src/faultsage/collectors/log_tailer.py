"""Log tailer (FR-8): only configured files, follows rotation, 8 KB line cap."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from faultsage.collectors.spool import SpoolWriter
from faultsage.paths import inside_root

LINE_CAP = 8192


@dataclass(slots=True)
class _TailState:
    inode: int = 0
    offset: int = 0
    line_no: int = 0


@dataclass(slots=True)
class LogTailer:
    root: Path
    files: list[str]
    patterns: list[str]
    writer: SpoolWriter
    _state: dict[str, _TailState] = field(default_factory=dict)
    _compiled: list[re.Pattern[str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._compiled = [re.compile(p) for p in self.patterns]
        for f in self.files:
            path = inside_root(self.root, f)
            st = _TailState()
            if path.exists():
                s = path.stat()
                st.inode, st.offset = s.st_ino, s.st_size  # start at end: only new lines
            self._state[f] = st

    def poll(self) -> int:
        """Read new lines from each file; return number of matches written."""
        matches = 0
        for f, st in self._state.items():
            path = inside_root(self.root, f)
            if not path.exists():
                continue
            s = path.stat()
            if s.st_ino != st.inode or s.st_size < st.offset:  # rotated or truncated
                st.inode, st.offset, st.line_no = s.st_ino, 0, 0
            if s.st_size == st.offset:
                continue
            with path.open("rb") as fh:
                fh.seek(st.offset)
                data = fh.read(4 * 1024 * 1024)
            last_nl = data.rfind(b"\n")
            if last_nl < 0:
                continue
            chunk, st.offset = data[: last_nl + 1], st.offset + last_nl + 1
            for raw in chunk.splitlines():
                st.line_no += 1
                text = raw[:LINE_CAP].decode("utf-8", errors="replace")
                for rx in self._compiled:
                    if rx.search(text):
                        self.writer.write(
                            "log_match",
                            {"file": f, "line_no": st.line_no, "pattern": rx.pattern, "text": text},
                        )
                        matches += 1
                        break
        return matches

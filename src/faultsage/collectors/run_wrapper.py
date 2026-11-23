"""faultsage run -- CMD (FR-7). Runs without a shell and records failures."""

from __future__ import annotations

import collections
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import IO

from faultsage.collectors.spool import SpoolWriter
from faultsage.config.loader import ProjectPaths
from faultsage.redact import redact

STDERR_TAIL = 400


def _python_entry(argv: list[str]) -> list[str] | None:
    """Return launcher args when argv is `python script.py` or `python -m module`."""
    if not argv:
        return None
    exe = Path(argv[0]).name.lower()
    if not (exe.startswith("python") or exe == "py" or argv[0] == sys.executable):
        return None
    rest = argv[1:]
    if len(rest) >= 2 and rest[0] == "-m":
        return rest
    if rest and rest[0].endswith(".py"):
        return rest
    return None


def _pump(src: IO[bytes], dst: IO[bytes], tail: collections.deque[str] | None) -> None:
    for chunk in iter(src.readline, b""):
        dst.write(chunk)
        dst.flush()
        if tail is not None:
            tail.append(chunk.decode("utf-8", errors="replace").rstrip("\n"))


def _other_spool_files(spool: Path) -> set[str]:
    """Spool files written by collectors other than this wrapper."""
    if not spool.is_dir():
        return set()
    return {f.name for f in spool.glob("*.jsonl") if not f.name.startswith("run_wrapper-")}


def run_and_record(paths: ProjectPaths, argv: list[str], timeout: float | None = None) -> int:
    """Run ``argv`` (no shell), stream output unchanged, write a run_result event on failure."""
    writer = SpoolWriter(paths.spool, "run_wrapper", paths.root)
    entry = _python_entry(argv)
    with tempfile.TemporaryDirectory(prefix="faultsage-") as tmp:
        exc_file = Path(tmp) / "exc.json"
        cmd = argv
        if entry is not None:
            cmd = [
                sys.executable if argv[0] == "python" else argv[0],
                "-m",
                "faultsage.collectors.launcher",
                str(exc_file),
                str(paths.root),
                *entry,
            ]
        before = _other_spool_files(paths.spool)
        start = time.monotonic()
        tail: collections.deque[str] = collections.deque(maxlen=STDERR_TAIL)
        try:
            proc = subprocess.Popen(  # noqa: S603  argv list, no shell (SR-7)
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, cwd=paths.root
            )
        except FileNotFoundError:
            print(f"faultsage: command not found: {argv[0]}", file=sys.stderr)
            return 127
        if proc.stdout is None or proc.stderr is None:  # PIPE was requested, so never None
            raise RuntimeError("subprocess pipes missing")
        t_out = threading.Thread(target=_pump, args=(proc.stdout, sys.stdout.buffer, None))
        t_err = threading.Thread(target=_pump, args=(proc.stderr, sys.stderr.buffer, tail))
        t_out.start()
        t_err.start()
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = proc.wait()
        t_out.join()
        t_err.join()
        duration = time.monotonic() - start
        if code != 0:
            exception = None
            if exc_file.exists():
                try:
                    exception = json.loads(exc_file.read_text(encoding="utf-8"))
                except ValueError:
                    exception = None
            if exception is None and _other_spool_files(paths.spool) - before:
                # Another collector (the pytest plugin) already recorded why this run failed;
                # a second "exited with code 1" incident would only be noise.
                return code
            writer.write(
                "run_result",
                {
                    "argv": [redact(a) for a in argv],
                    "exit_code": code,
                    "duration_s": round(duration, 3),
                    "stderr_tail": redact("\n".join(tail)),
                    "exception": exception,
                },
            )
        return code

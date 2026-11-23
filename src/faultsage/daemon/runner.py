"""Daemon lifecycle (F2): lock file, ingest loop, log tailer, file watcher, control commands.

Control is file based so the CLI never needs the dashboard token: `faultsage pause` writes
`.faultsage/control` and the loop picks it up within one poll.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from faultsage.collectors.log_tailer import LogTailer
from faultsage.collectors.spool import SpoolWriter
from faultsage.config.loader import ProjectPaths
from faultsage.daemon.service import Workspace
from faultsage.selfmon import hook as selfmon
from faultsage.storage import repo_events
from faultsage.storage.db import tx

POLL_S = 0.25
_log = logging.getLogger("faultsage.daemon")


class DaemonLockedError(RuntimeError):
    pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_lock(paths: ProjectPaths) -> dict[str, Any] | None:
    try:
        data: dict[str, Any] = json.loads(paths.lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if _pid_alive(int(data.get("pid", 0))) else None


def write_lock(paths: ProjectPaths, port: int, state: str) -> None:
    paths.lock.write_text(
        json.dumps({"pid": os.getpid(), "port": port, "state": state}), encoding="utf-8"
    )


def send_control(paths: ProjectPaths, command: str) -> bool:
    if read_lock(paths) is None:
        return False
    paths.control.write_text(command, encoding="utf-8")
    return True


class Daemon:
    def __init__(self, ws: Workspace, port: int) -> None:
        self.ws = ws
        self.port = port
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._watcher: Any = None
        self._tailer: LogTailer | None = None
        self.on_stop: list[Any] = []

    def start(self) -> None:
        existing = read_lock(self.ws.paths)
        if existing and existing.get("pid") != os.getpid():
            raise DaemonLockedError(
                f"Another FaultSage daemon (PID {existing['pid']}) is watching this project. "
                "Run faultsage stop first."
            )
        with tx(self.ws.conn):
            self.ws.session_id = repo_events.start_session(
                self.ws.conn, self.ws.project_id, self.ws.cfg.signals.model_dump()
            )
        self.ws.state = "running"
        self.ws.started_at = time.time()
        write_lock(self.ws.paths, self.port, "running")
        sig = self.ws.cfg.signals
        if sig.logs:
            self._tailer = LogTailer(
                self.ws.paths.root,
                sig.logs,
                sig.log_patterns,
                SpoolWriter(self.ws.paths.spool, "log_tailer", self.ws.paths.root),
            )
        if sig.file_watch:
            try:
                from faultsage.collectors.fs_watcher import FsWatcher

                self._watcher = FsWatcher(
                    self.ws.paths.root,
                    SpoolWriter(self.ws.paths.spool, "fs_watcher", self.ws.paths.root),
                    on_change=self._wake.set,
                )
                self._watcher.start()
            except Exception as e:
                selfmon.record(e, "fs_watcher")
                self._watcher = None
        self._thread = threading.Thread(target=self._loop, name="faultsage-ingest", daemon=True)
        self._thread.start()

    def set_state(self, state: str) -> None:
        self.ws.state = state
        if self.ws.session_id:
            with tx(self.ws.conn):
                repo_events.set_session_state(self.ws.conn, self.ws.session_id, state)
        if state != "stopped":
            write_lock(self.ws.paths, self.port, state)
        self.ws.emit("status.changed", self.ws.status())

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._handle_control()
                if self.ws.state == "running":
                    if self._tailer is not None:
                        self._tailer.poll()
                    self.ws.ingest()
            except Exception as e:
                selfmon.record(e, "ingest_loop")
            self._wake.wait(POLL_S)
            self._wake.clear()

    def _handle_control(self) -> None:
        p = self.ws.paths.control
        if not p.exists():
            return
        cmd = p.read_text(encoding="utf-8").strip()
        with contextlib.suppress(OSError):
            p.unlink()
        if cmd == "pause":
            self.set_state("paused")
        elif cmd == "resume":
            self.set_state("running")
        elif cmd == "stop":
            self.stop()

    def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        self._wake.set()
        if self._watcher is not None:
            self._watcher.stop()
        self.set_state("stopped")
        with contextlib.suppress(OSError):
            self.ws.paths.lock.unlink()
        for cb in self.on_stop:
            cb()


def wait_for_spool_drain(paths: ProjectPaths, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and any(Path(paths.spool).glob("*.jsonl")):
        time.sleep(0.1)

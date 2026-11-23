"""Spool -> events table -> incidents (ARCHITECTURE section 4.1)."""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from faultsage.daemon.grouping import signature, title_for
from faultsage.models.core import ExceptionInfo
from faultsage.models.events import Event, iso, validate_event
from faultsage.storage import repo_events, repo_incidents
from faultsage.storage.db import tx

if TYPE_CHECKING:
    from faultsage.daemon.service import Workspace

_log = logging.getLogger("faultsage.daemon")
MAX_LINE = 1_000_000


@dataclass(slots=True)
class IngestResult:
    events: int = 0
    rejected: int = 0
    touched_incidents: set[int] = field(default_factory=set)
    created_incidents: set[int] = field(default_factory=set)
    passed_tests: set[str] = field(default_factory=set)


def _reject(ws: Workspace, src: Path, line: str, reason: str) -> None:
    ws.paths.rejected.mkdir(parents=True, exist_ok=True)
    with (ws.paths.rejected / f"{src.stem}.rejected.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"reason": reason[:2000], "line": line[:MAX_LINE]}) + "\n")


def _failure(ev: Event) -> tuple[bool, ExceptionInfo | None, str]:
    b = ev.body
    if ev.kind == "test_result":
        failed = b["outcome"] in ("failed", "error")
        exc = ExceptionInfo.model_validate(b["exception"]) if b.get("exception") else None
        if failed and exc is None and b.get("longrepr_text"):
            from faultsage.analysis.traceback_parser import parse_pytest

            exc = parse_pytest(b["longrepr_text"])
        return failed, exc, str(b["node_id"])
    if ev.kind == "run_result":
        exc = ExceptionInfo.model_validate(b["exception"]) if b.get("exception") else None
        if exc is None and b.get("stderr_tail"):
            from faultsage.analysis.traceback_parser import parse_cpython

            exc = parse_cpython(b["stderr_tail"])
        return b["exit_code"] != 0, exc, " ".join(b["argv"][:3])
    if ev.kind == "log_match":
        return True, None, f"{b['file']}:{b['pattern']}"
    return False, None, ""


def ingest_once(ws: Workspace) -> IngestResult:
    """Read every complete spool line, store it idempotently, group failures. Spool files are
    deleted after successful ingest; a partial last line is kept for the next pass."""
    res = IngestResult()
    files = sorted(p for p in ws.paths.spool.glob("*.jsonl") if p.is_file())
    files += sorted(ws.paths.spool.glob("*.ingesting"))  # left over from a crash
    for original in files:
        # Rename first: writers open by name per write, so new lines go to a fresh file.
        src = original if original.suffix == ".ingesting" else original.with_suffix(".ingesting")
        try:
            if src != original:
                original.replace(src)
            data = src.read_bytes()
        except OSError:
            continue
        end = data.rfind(b"\n")
        complete, rest = data[: end + 1], data[end + 1 :]
        for raw in complete.splitlines():
            line = raw.decode("utf-8", errors="replace")
            if not line.strip():
                continue
            if len(line) > MAX_LINE:
                _reject(ws, src, line, "line too long")
                res.rejected += 1
                continue
            try:
                ev = validate_event(json.loads(line))
            except (ValueError, ValidationError) as exc:
                _reject(ws, src, line, str(exc))
                res.rejected += 1
                continue
            _store(ws, src.name, ev, res)
        if rest.strip():
            # A partial last line means the writer died mid-write. Keep it for inspection.
            _reject(ws, src, rest.decode("utf-8", errors="replace"), "incomplete last line")
            res.rejected += 1
        with contextlib.suppress(OSError):
            src.unlink()
    return res


def _store(ws: Workspace, source_file: str, ev: Event, res: IngestResult) -> None:
    occurred = iso(ev.occurred_at)
    with tx(ws.conn) as conn:
        event_id = repo_events.insert_event(
            conn, ws.project_id, ws.session_id, ev.kind, occurred, source_file, ev.body
        )
        if event_id is None:
            return  # duplicate (idempotent ingest)
        res.events += 1
        if ev.kind == "checkpoint":
            repo_events.insert_checkpoint(conn, ws.project_id, ev.body, occurred, event_id)
            return
        if ev.kind == "test_result" and ev.body["outcome"] == "passed":
            res.passed_tests.add(ev.body["node_id"])
            ws.test_outcomes[ev.body["node_id"]] = "passed"
            return
        failed, exc, fallback = _failure(ev)
        if not failed:
            return
        if ev.kind == "test_result":
            ws.test_outcomes[ev.body["node_id"]] = "failed"
        sig = signature(exc, fallback)
        head = ws.git_head()
        inc = repo_incidents.find_open_by_signature(conn, ws.project_id, sig)
        if inc is not None:
            repo_incidents.add_occurrence(conn, inc["id"], event_id, head, occurred, bump=True)
            if inc["status"] in ("fix_applied", "verified"):
                repo_incidents.set_status(conn, inc["id"], "reopened")
            res.touched_incidents.add(int(inc["id"]))
            return
        closed = repo_incidents.find_closed_by_signature(conn, ws.project_id, sig)
        if closed is not None:
            # FR-12/13: a resolved incident reopens on recurrence.
            repo_incidents.set_status(conn, closed["id"], "reopened")
            repo_incidents.add_occurrence(conn, closed["id"], event_id, head, occurred, bump=True)
            res.touched_incidents.add(int(closed["id"]))
            return
        title = title_for(ev.kind, ev.body, exc)
        iid = repo_incidents.create_incident(
            conn, ws.project_id, sig, title[:300], exc.type if exc else None, occurred
        )
        repo_incidents.add_occurrence(conn, iid, event_id, head, occurred, bump=False)
        res.touched_incidents.add(iid)
        res.created_incidents.add(iid)

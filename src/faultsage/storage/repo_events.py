"""Projects, watch sessions, events, checkpoints, graph snapshots, scans."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from faultsage.storage.db import now_iso


def upsert_project(
    conn: sqlite3.Connection, name: str, root: str, python_version: str, cfg_hash: str
) -> int:
    row = conn.execute("SELECT id FROM projects WHERE root_path = ?", (root,)).fetchone()
    if row:
        conn.execute(
            "UPDATE projects SET name = ?, python_version = ?, config_hash = ? WHERE id = ?",
            (name, python_version, cfg_hash, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO projects(name, root_path, python_version, created_at, config_hash) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, root, python_version, now_iso(), cfg_hash),
    )
    return int(cur.lastrowid or 0)


def get_project(conn: sqlite3.Connection, project_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    return row


def start_session(conn: sqlite3.Connection, project_id: int, signals: dict[str, Any]) -> int:
    cur = conn.execute(
        "INSERT INTO watch_sessions(project_id, started_at, state, signals_json) VALUES (?, ?, ?, ?)",
        (project_id, now_iso(), "running", json.dumps(signals)),
    )
    return int(cur.lastrowid or 0)


def set_session_state(conn: sqlite3.Connection, session_id: int, state: str) -> None:
    ended = now_iso() if state in ("stopped", "crashed") else None
    conn.execute(
        "UPDATE watch_sessions SET state = ?, ended_at = COALESCE(?, ended_at) WHERE id = ?",
        (state, ended, session_id),
    )


def insert_event(
    conn: sqlite3.Connection,
    project_id: int,
    session_id: int | None,
    kind: str,
    occurred_at: str,
    source_file: str,
    payload: dict[str, Any],
) -> int | None:
    """Idempotent insert (UNIQUE source_file + payload hash). Returns None for duplicates."""
    payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    sha = hashlib.sha256(f"{occurred_at}|{payload_json}".encode()).hexdigest()
    cur = conn.execute(
        "INSERT OR IGNORE INTO events(project_id, session_id, kind, occurred_at, source_file, "
        "payload_json, payload_sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (project_id, session_id, kind, occurred_at, source_file, payload_json, sha),
    )
    return int(cur.lastrowid) if cur.rowcount == 1 and cur.lastrowid else None


def event_payload(conn: sqlite3.Connection, event_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT payload_json FROM events WHERE id = ?", (event_id,)).fetchone()
    return json.loads(row["payload_json"]) if row else None


def recent_events(
    conn: sqlite3.Connection, project_id: int, kind: str, limit: int = 50
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM events WHERE project_id = ? AND kind = ? ORDER BY occurred_at DESC, id DESC "
            "LIMIT ?",
            (project_id, kind, limit),
        )
    )


def delete_old_events(conn: sqlite3.Connection, project_id: int, days: int) -> int:
    """FR-35 retention. Keeps events referenced by incidents, evidence or checkpoints."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    cur = conn.execute(
        "DELETE FROM events WHERE project_id = ? AND occurred_at < ? "
        "AND id NOT IN (SELECT event_id FROM occurrences) "
        "AND id NOT IN (SELECT event_id FROM evidence WHERE event_id IS NOT NULL) "
        "AND id NOT IN (SELECT event_id FROM checkpoints WHERE event_id IS NOT NULL)",
        (project_id, cutoff),
    )
    return cur.rowcount


def insert_checkpoint(
    conn: sqlite3.Connection, project_id: int, body: dict[str, Any], recorded_at: str, event_id: int
) -> None:
    conn.execute(
        "INSERT INTO checkpoints(project_id, step, recorded_at, object_type, shape_json, "
        "columns_json, event_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            project_id,
            body["step"],
            recorded_at,
            body["object_type"],
            json.dumps(body.get("shape")),
            json.dumps(body.get("columns", [])),
            event_id,
        ),
    )


def latest_checkpoints(conn: sqlite3.Connection, project_id: int) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        "SELECT c.* FROM checkpoints c JOIN (SELECT step, MAX(id) AS mid FROM checkpoints "
        "WHERE project_id = ? GROUP BY step) m ON c.id = m.mid",
        (project_id,),
    )
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out[r["step"]] = {
            "step": r["step"],
            "recorded_at": r["recorded_at"],
            "object_type": r["object_type"],
            "shape": json.loads(r["shape_json"]) if r["shape_json"] else None,
            "columns": json.loads(r["columns_json"]) if r["columns_json"] else [],
        }
    return out


def save_graph(
    conn: sqlite3.Connection, project_id: int, kind: str, files_hash: str, graph: dict[str, Any]
) -> None:
    conn.execute(
        "DELETE FROM graph_snapshots WHERE project_id = ? AND kind = ?", (project_id, kind)
    )
    conn.execute(
        "INSERT INTO graph_snapshots(project_id, kind, built_at, files_hash, graph_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (project_id, kind, now_iso(), files_hash, json.dumps(graph)),
    )


def load_graph(
    conn: sqlite3.Connection, project_id: int, kind: str
) -> tuple[str, dict[str, Any]] | None:
    row = conn.execute(
        "SELECT files_hash, graph_json FROM graph_snapshots WHERE project_id = ? AND kind = ? "
        "ORDER BY id DESC LIMIT 1",
        (project_id, kind),
    ).fetchone()
    return (row["files_hash"], json.loads(row["graph_json"])) if row else None


def create_scan(conn: sqlite3.Connection, project_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO scan_runs(project_id, started_at) VALUES (?, ?)", (project_id, now_iso())
    )
    return int(cur.lastrowid or 0)


def finish_scan(conn: sqlite3.Connection, scan_id: int, findings: list[dict[str, Any]]) -> None:
    for f in findings:
        conn.execute(
            "INSERT INTO scan_findings(scan_id, severity, rule, file_path, line, message) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (scan_id, f["severity"], f["rule"], f.get("file_path"), f.get("line"), f["message"]),
        )
    conn.execute(
        "UPDATE scan_runs SET finished_at = ?, findings_count = ? WHERE id = ?",
        (now_iso(), len(findings), scan_id),
    )


def get_scan(conn: sqlite3.Connection, scan_id: int) -> dict[str, Any] | None:
    run = conn.execute("SELECT * FROM scan_runs WHERE id = ?", (scan_id,)).fetchone()
    if run is None:
        return None
    findings = [
        dict(r)
        for r in conn.execute(
            "SELECT severity, rule, file_path, line, message FROM scan_findings WHERE scan_id = ? "
            "ORDER BY file_path, line",
            (scan_id,),
        )
    ]
    return {**dict(run), "findings": findings}


def latest_scan_id(conn: sqlite3.Connection, project_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM scan_runs WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)
    ).fetchone()
    return int(row["id"]) if row else None


def purge(conn: sqlite3.Connection, project_id: int) -> None:
    """FR-36 purge (non --all): events, incidents and their children. Approvals stay (audit)."""
    for stmt in (
        "DELETE FROM evidence WHERE hypothesis_id IN (SELECT h.id FROM hypotheses h JOIN incidents i "
        "ON h.incident_id = i.id WHERE i.project_id = ?)",
        "DELETE FROM hypotheses WHERE incident_id IN (SELECT id FROM incidents WHERE project_id = ?)",
        "DELETE FROM locations WHERE incident_id IN (SELECT id FROM incidents WHERE project_id = ?)",
        "DELETE FROM impacts WHERE incident_id IN (SELECT id FROM incidents WHERE project_id = ?)",
        "DELETE FROM verifications WHERE incident_id IN (SELECT id FROM incidents WHERE project_id = ?)",
        "DELETE FROM occurrences WHERE incident_id IN (SELECT id FROM incidents WHERE project_id = ?)",
        "DELETE FROM checkpoints WHERE project_id = ?",
        "DELETE FROM scan_findings WHERE scan_id IN (SELECT id FROM scan_runs WHERE project_id = ?)",
        "DELETE FROM scan_runs WHERE project_id = ?",
        "DELETE FROM graph_snapshots WHERE project_id = ?",
    ):
        conn.execute(stmt, (project_id,))
    # Suggestions referenced by approvals are kept so the audit trail stays valid.
    conn.execute(
        "DELETE FROM suggestions WHERE incident_id IN (SELECT id FROM incidents WHERE project_id = ?) "
        "AND id NOT IN (SELECT suggestion_id FROM approvals)",
        (project_id,),
    )
    conn.execute(
        "DELETE FROM incidents WHERE project_id = ? AND id NOT IN (SELECT incident_id FROM suggestions)",
        (project_id,),
    )
    conn.execute(
        "DELETE FROM events WHERE project_id = ? AND id NOT IN (SELECT event_id FROM occurrences)",
        (project_id,),
    )

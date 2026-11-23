"""Incidents and their children: occurrences, locations, hypotheses, evidence, impacts,
suggestions, approvals, verifications."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from faultsage.models.core import (
    Approval,
    CaseFile,
    EvidenceItem,
    Hypothesis,
    ImpactNode,
    IncidentSummary,
    Location,
    Suggestion,
    TestOutcome,
    TimelineEntry,
    Verification,
)
from faultsage.storage.db import now_iso

OPEN_STATES = ("open", "investigating", "fix_proposed", "fix_applied", "verified", "reopened")


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def find_open_by_signature(
    conn: sqlite3.Connection, project_id: int, signature: str
) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM incidents WHERE project_id = ? AND signature = ? "
        "AND status NOT IN ('resolved','dismissed')",
        (project_id, signature),
    ).fetchone()
    return row


def find_closed_by_signature(
    conn: sqlite3.Connection, project_id: int, signature: str
) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM incidents WHERE project_id = ? AND signature = ? AND status = 'resolved' "
        "ORDER BY id DESC LIMIT 1",
        (project_id, signature),
    ).fetchone()
    return row


def create_incident(
    conn: sqlite3.Connection,
    project_id: int,
    signature: str,
    title: str,
    exc_type: str | None,
    occurred_at: str,
) -> int:
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO incidents(project_id, signature, title, status, exception_type, first_seen_at, "
        "last_seen_at, occurrence_count, created_at, updated_at) VALUES (?, ?, ?, 'open', ?, ?, ?, 1, ?, ?)",
        (project_id, signature, title, exc_type, occurred_at, occurred_at, ts, ts),
    )
    return int(cur.lastrowid or 0)


def add_occurrence(
    conn: sqlite3.Connection,
    incident_id: int,
    event_id: int,
    git_head: str | None,
    occurred_at: str,
    *,
    bump: bool,
) -> None:
    conn.execute(
        "INSERT INTO occurrences(incident_id, event_id, git_head, occurred_at) VALUES (?, ?, ?, ?)",
        (incident_id, event_id, git_head, occurred_at),
    )
    if bump:
        conn.execute(
            "UPDATE incidents SET occurrence_count = occurrence_count + 1, last_seen_at = ?, "
            "updated_at = ? WHERE id = ?",
            (occurred_at, now_iso(), incident_id),
        )


def set_status(conn: sqlite3.Connection, incident_id: int, status: str) -> None:
    conn.execute(
        "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_iso(), incident_id),
    )


def set_analysis_error(conn: sqlite3.Connection, incident_id: int, error: str | None) -> None:
    conn.execute(
        "UPDATE incidents SET analysis_error = ?, updated_at = ? WHERE id = ?",
        (error, now_iso(), incident_id),
    )


def get_incident(conn: sqlite3.Connection, incident_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM incidents WHERE id = ?", (incident_id,)
    ).fetchone()
    return row


def occurrence_events(conn: sqlite3.Connection, incident_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT e.id, e.kind, e.occurred_at, e.payload_json, o.git_head FROM occurrences o "
        "JOIN events e ON e.id = o.event_id WHERE o.incident_id = ? ORDER BY o.id",
        (incident_id,),
    )
    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "occurred_at": r["occurred_at"],
            "payload": json.loads(r["payload_json"]),
            "git_head": r["git_head"],
        }
        for r in rows
    ]


def list_incidents(
    conn: sqlite3.Connection,
    project_id: int,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    cursor: int | None = None,
) -> tuple[list[IncidentSummary], int | None]:
    sql = (
        "SELECT i.*, (SELECT h.certainty FROM hypotheses h WHERE h.incident_id = i.id "
        "ORDER BY h.rank LIMIT 1) AS top_certainty FROM incidents i WHERE i.project_id = ?"
    )
    args: list[Any] = [project_id]
    if status == "open_any":
        sql += " AND i.status NOT IN ('resolved', 'dismissed')"
    elif status:
        sql += " AND i.status = ?"
        args.append(status)
    if q:
        sql += " AND (i.title LIKE ? ESCAPE '\\' OR i.signature LIKE ? ESCAPE '\\')"
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        args.extend([like, like])
    if cursor:
        sql += " AND i.id < ?"
        args.append(cursor)
    sql += " ORDER BY i.id DESC LIMIT ?"
    args.append(limit + 1)
    rows = list(conn.execute(sql, args))
    items = [
        IncidentSummary(
            id=r["id"],
            title=r["title"],
            status=r["status"],
            exception_type=r["exception_type"],
            top_certainty=r["top_certainty"],
            first_seen_at=_dt(r["first_seen_at"]),
            last_seen_at=_dt(r["last_seen_at"]),
            occurrence_count=r["occurrence_count"],
        )
        for r in rows[:limit]
    ]
    next_cursor = items[-1].id if len(rows) > limit and items else None
    return items, next_cursor


def summary(conn: sqlite3.Connection, incident_id: int) -> IncidentSummary | None:
    row = get_incident(conn, incident_id)
    if row is None:
        return None
    items, _ = list_incidents(conn, row["project_id"], q=None, limit=100000)
    return next((i for i in items if i.id == incident_id), None)


def count_open(conn: sqlite3.Connection, project_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM incidents WHERE project_id = ? "
        "AND status NOT IN ('resolved', 'dismissed')",
        (project_id,),
    ).fetchone()
    return int(row[0])


def replace_analysis(
    conn: sqlite3.Connection,
    incident_id: int,
    raise_site: Location | None,
    raise_hash: str | None,
    hypotheses: list[Hypothesis],
    impacts: list[ImpactNode],
    suggestions: list[Suggestion],
    file_hashes: dict[str, str],
) -> None:
    """Replace the analysis output for an incident. Suggestions already approved are kept."""
    conn.execute(
        "DELETE FROM evidence WHERE hypothesis_id IN (SELECT id FROM hypotheses WHERE incident_id = ?)",
        (incident_id,),
    )
    conn.execute("DELETE FROM hypotheses WHERE incident_id = ?", (incident_id,))
    conn.execute("DELETE FROM locations WHERE incident_id = ?", (incident_id,))
    conn.execute("DELETE FROM impacts WHERE incident_id = ?", (incident_id,))
    conn.execute(
        "DELETE FROM suggestions WHERE incident_id = ? AND state IN ('proposed','stale') "
        "AND id NOT IN (SELECT suggestion_id FROM approvals)",
        (incident_id,),
    )
    if raise_site is not None:
        _insert_location(conn, incident_id, "raise_site", raise_site, raise_hash)
    for h in hypotheses:
        loc_id = None
        if h.location is not None:
            loc_id = _insert_location(
                conn, incident_id, "candidate", h.location, file_hashes.get(h.location.file_path)
            )
        cur = conn.execute(
            "INSERT INTO hypotheses(incident_id, location_id, pipeline_step, rank, score, certainty, "
            "claim, features_json, weights_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                incident_id,
                loc_id,
                h.pipeline_step,
                h.rank,
                h.score,
                h.certainty,
                h.claim,
                json.dumps(h.features),
                h.weights_version,
            ),
        )
        hid = cur.lastrowid
        for e in h.evidence:
            conn.execute(
                "INSERT INTO evidence(hypothesis_id, source, stance, summary, detail_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (hid, e.source, e.stance, e.summary, json.dumps(e.detail)),
            )
    for imp in impacts:
        conn.execute(
            "INSERT INTO impacts(incident_id, node_kind, node_name, relation, basis, depth) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (incident_id, imp.kind, imp.name, imp.relation, imp.basis, imp.depth),
        )
    for s in suggestions:
        conn.execute(
            "INSERT INTO suggestions(incident_id, origin, rule_id, explanation, patch_diff, "
            "base_hashes_json, verify_node_ids_json, state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                incident_id,
                s.origin,
                s.rule_id,
                s.explanation,
                s.patch_diff,
                json.dumps(s.base_hashes),
                json.dumps(s.verify_node_ids),
                s.state,
                now_iso(),
            ),
        )


def _insert_location(
    conn: sqlite3.Connection, incident_id: int, role: str, loc: Location, sha: str | None
) -> int:
    excerpt = json.dumps(loc.excerpt) if loc.excerpt else None
    cur = conn.execute(
        "INSERT INTO locations(incident_id, role, file_path, line, function, class_name, file_sha256, "
        "excerpt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            incident_id,
            role,
            loc.file_path,
            loc.line if loc.available else None,
            loc.function,
            loc.class_name,
            sha,
            excerpt,
        ),
    )
    return int(cur.lastrowid or 0)


def _location(r: sqlite3.Row) -> Location:
    excerpt = json.loads(r["excerpt"]) if r["excerpt"] else None
    return Location(
        file_path=r["file_path"],
        line=r["line"],
        function=r["function"],
        class_name=r["class_name"],
        excerpt=[(int(a), str(b)) for a, b in excerpt] if excerpt else None,
        available=r["line"] is not None,
    )


def get_suggestion(conn: sqlite3.Connection, suggestion_id: int) -> tuple[int, Suggestion] | None:
    r = conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    return (int(r["incident_id"]), _suggestion(r)) if r else None


def _suggestion(r: sqlite3.Row) -> Suggestion:
    node_ids = json.loads(r["verify_node_ids_json"])
    hashes = json.loads(r["base_hashes_json"]) if r["base_hashes_json"] else {}
    return Suggestion(
        id=r["id"],
        origin=r["origin"],
        rule_id=r["rule_id"],
        explanation=r["explanation"],
        patch_diff=r["patch_diff"],
        base_hashes=hashes,
        files=sorted(hashes),
        verify_node_ids=node_ids,
        verify_command=("python -m pytest " + " ".join(node_ids)) if node_ids else "",
        state=r["state"],
    )


def set_suggestion_state(conn: sqlite3.Connection, suggestion_id: int, state: str) -> None:
    conn.execute("UPDATE suggestions SET state = ? WHERE id = ?", (state, suggestion_id))


def create_approval(conn: sqlite3.Connection, suggestion_id: int, via: str, patch_sha: str) -> int:
    cur = conn.execute(
        "INSERT INTO approvals(suggestion_id, approved_via, approved_at, patch_sha256, outcome) "
        "VALUES (?, ?, ?, ?, 'pending')",
        (suggestion_id, via, now_iso(), patch_sha),
    )
    return int(cur.lastrowid or 0)


def finish_approval(
    conn: sqlite3.Connection, approval_id: int, outcome: str, detail: str | None, backup: str | None
) -> Approval:
    conn.execute(
        "UPDATE approvals SET outcome = ?, outcome_detail = ?, backup_path = ? WHERE id = ?",
        (outcome, detail, backup, approval_id),
    )
    r = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    return Approval(
        id=r["id"],
        suggestion_id=r["suggestion_id"],
        outcome=r["outcome"],
        outcome_detail=r["outcome_detail"],
        backup_path=r["backup_path"],
    )


def create_verification(conn: sqlite3.Connection, incident_id: int) -> int:
    cur = conn.execute(
        "INSERT INTO verifications(incident_id, started_at, tests_json) VALUES (?, ?, '[]')",
        (incident_id, now_iso()),
    )
    return int(cur.lastrowid or 0)


def finish_verification(
    conn: sqlite3.Connection, verification_id: int, result: str, tests: list[TestOutcome]
) -> None:
    conn.execute(
        "UPDATE verifications SET finished_at = ?, result = ?, tests_json = ? WHERE id = ?",
        (now_iso(), result, json.dumps([t.model_dump() for t in tests]), verification_id),
    )


def running_verification(conn: sqlite3.Connection, incident_id: int) -> int | None:
    r = conn.execute(
        "SELECT id FROM verifications WHERE incident_id = ? AND finished_at IS NULL", (incident_id,)
    ).fetchone()
    return int(r["id"]) if r else None


def get_verification(conn: sqlite3.Connection, verification_id: int) -> Verification | None:
    r = conn.execute("SELECT * FROM verifications WHERE id = ?", (verification_id,)).fetchone()
    return _verification(r) if r else None


def _verification(r: sqlite3.Row) -> Verification:
    return Verification(
        id=r["id"],
        incident_id=r["incident_id"],
        result=r["result"],
        tests=[TestOutcome(**t) for t in json.loads(r["tests_json"])],
        started_at=_dt(r["started_at"]),
        finished_at=_dt(r["finished_at"]) if r["finished_at"] else None,
    )


def case_file(conn: sqlite3.Connection, incident_id: int) -> CaseFile | None:
    inc = get_incident(conn, incident_id)
    if inc is None:
        return None
    occ = occurrence_events(conn, incident_id)
    exception = None
    failing: list[str] = []
    for o in occ:
        p = o["payload"]
        if p.get("exception") and exception is None:
            exception = p["exception"]
        if p.get("node_id") and p["node_id"] not in failing:
            failing.append(p["node_id"])
    locs = {
        r["id"]: r
        for r in conn.execute("SELECT * FROM locations WHERE incident_id = ?", (incident_id,))
    }
    raise_site = next((_location(r) for r in locs.values() if r["role"] == "raise_site"), None)
    hyps: list[Hypothesis] = []
    for h in conn.execute(
        "SELECT * FROM hypotheses WHERE incident_id = ? ORDER BY rank", (incident_id,)
    ):
        ev = [
            EvidenceItem(
                source=e["source"],
                stance=e["stance"],
                summary=e["summary"],
                detail=json.loads(e["detail_json"]),
            )
            for e in conn.execute(
                "SELECT * FROM evidence WHERE hypothesis_id = ? ORDER BY id", (h["id"],)
            )
        ]
        loc_row = locs.get(h["location_id"])
        hyps.append(
            Hypothesis(
                rank=h["rank"],
                score=h["score"],
                certainty=h["certainty"],
                claim=h["claim"],
                location=_location(loc_row) if loc_row is not None else None,
                pipeline_step=h["pipeline_step"],
                evidence=ev,
                weights_version=h["weights_version"],
                features=json.loads(h["features_json"]),
            )
        )
    impacts = [
        ImpactNode(
            kind=r["node_kind"],
            name=r["node_name"],
            relation=r["relation"],
            basis=r["basis"],
            depth=r["depth"],
        )
        for r in conn.execute(
            "SELECT * FROM impacts WHERE incident_id = ? ORDER BY depth, node_name", (incident_id,)
        )
    ]
    suggestions = [
        _suggestion(r)
        for r in conn.execute(
            "SELECT * FROM suggestions WHERE incident_id = ? ORDER BY id", (incident_id,)
        )
    ]
    verifs = [
        _verification(r)
        for r in conn.execute(
            "SELECT * FROM verifications WHERE incident_id = ? ORDER BY id", (incident_id,)
        )
    ]
    timeline: list[TimelineEntry] = []
    for o in occ:
        p = o["payload"]
        what = p.get("node_id") or " ".join(p.get("argv", [])) or o["kind"]
        timeline.append(
            TimelineEntry(at=_dt(o["occurred_at"]), kind="occurrence", text=f"Failed: {what}")
        )
    for a in conn.execute(
        "SELECT a.* FROM approvals a JOIN suggestions s ON s.id = a.suggestion_id WHERE s.incident_id = ?",
        (incident_id,),
    ):
        timeline.append(
            TimelineEntry(
                at=_dt(a["approved_at"]),
                kind="approval",
                text=f"Patch S-{a['suggestion_id']} approved via {a['approved_via']}: {a['outcome']}",
            )
        )
    for v in verifs:
        timeline.append(
            TimelineEntry(
                at=v.started_at,
                kind="verification",
                text=f"Verification V-{v.id}: {v.result or 'running'}",
            )
        )
    timeline.sort(key=lambda t: t.at)
    missing = []
    if not any(e.source == "coverage" for h in hyps for e in h.evidence):
        missing.append("coverage data")
    if not any(e.source == "git" for h in hyps for e in h.evidence):
        missing.append("git history")
    from faultsage.models.core import ExceptionInfo

    return CaseFile(
        incident_id=inc["id"],
        title=inc["title"],
        status=inc["status"],
        exception=ExceptionInfo.model_validate(exception) if exception else None,
        failing_tests=failing,
        raise_site=raise_site,
        hypotheses=hyps,
        impacts=impacts,
        suggestions=suggestions,
        verifications=verifs,
        timeline=timeline,
        first_seen_at=_dt(inc["first_seen_at"]),
        last_seen_at=_dt(inc["last_seen_at"]),
        occurrence_count=inc["occurrence_count"],
        analysis_error=inc["analysis_error"],
        missing_evidence=missing,
    )


def prior_incidents_at(
    conn: sqlite3.Connection, project_id: int, file_path: str, exclude: int
) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT l.incident_id FROM locations l JOIN incidents i ON i.id = l.incident_id "
        "WHERE i.project_id = ? AND l.file_path = ? AND l.incident_id != ?",
        (project_id, file_path, exclude),
    )
    return [int(r[0]) for r in rows]

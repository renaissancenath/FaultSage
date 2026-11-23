"""All cloud SQL. Parameterised only; table and column names never come from input."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Connection

from faultsage.cloud.storage.db import ex, insert, now_iso, one, q


def _in(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---- users ----------------------------------------------------------------------------------


def user_by_email(c: Connection, email: str) -> dict[str, Any] | None:
    return one(c, "SELECT * FROM users WHERE email = :e", e=email.lower())


def user_by_id(c: Connection, uid: int) -> dict[str, Any] | None:
    return one(c, "SELECT * FROM users WHERE id = :i", i=uid)


def user_by_github(c: Connection, gid: str) -> dict[str, Any] | None:
    return one(c, "SELECT * FROM users WHERE github_id = :g", g=gid)


def create_user(
    c: Connection,
    email: str,
    name: str,
    password_hash: str | None,
    github_id: str | None = None,
    verified: bool = False,
) -> int:
    return insert(
        c,
        "INSERT INTO users(email, name, password_hash, github_id, email_verified_at, created_at) "
        "VALUES (:e, :n, :p, :g, :v, :t)",
        e=email.lower(),
        n=name[:120],
        p=password_hash,
        g=github_id,
        v=now_iso() if verified else None,
        t=now_iso(),
    )


def set_password(c: Connection, uid: int, password_hash: str) -> None:
    ex(
        c,
        "UPDATE users SET password_hash = :p, failed_logins = 0, locked_until = NULL WHERE id = :i",
        p=password_hash,
        i=uid,
    )


def record_login_failure(c: Connection, uid: int, locked_until: str | None) -> None:
    ex(
        c,
        "UPDATE users SET failed_logins = failed_logins + 1, locked_until = :l WHERE id = :i",
        l=locked_until,
        i=uid,
    )


def reset_login_failures(c: Connection, uid: int) -> None:
    ex(c, "UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = :i", i=uid)


def mark_verified(c: Connection, uid: int) -> None:
    ex(
        c,
        "UPDATE users SET email_verified_at = COALESCE(email_verified_at, :t) WHERE id = :i",
        t=now_iso(),
        i=uid,
    )


def link_github(c: Connection, uid: int, gid: str) -> None:
    ex(c, "UPDATE users SET github_id = :g WHERE id = :i", g=gid, i=uid)


def update_name(c: Connection, uid: int, name: str) -> None:
    ex(c, "UPDATE users SET name = :n WHERE id = :i", n=name[:120], i=uid)


def delete_user(c: Connection, uid: int) -> None:
    """Account deletion: personal data removed immediately (02_LOGIN-RULES: within 30 days)."""
    owned = q(c, "SELECT org_id FROM memberships WHERE user_id = :u AND role = 'owner'", u=uid)
    for row in owned:
        others = one(
            c,
            "SELECT COUNT(*) AS n FROM memberships WHERE org_id = :o AND user_id != :u",
            o=row["org_id"],
            u=uid,
        )
        if others and int(others["n"]) == 0:
            ex(c, "DELETE FROM orgs WHERE id = :o", o=row["org_id"])  # sole owner: org goes too
    ex(c, "DELETE FROM users WHERE id = :i", i=uid)


# ---- sessions -------------------------------------------------------------------------------


def create_session(
    c: Connection, id_hash: str, uid: int, csrf_hash: str, days: int, ua: str
) -> None:
    t = now_iso()
    ex(
        c,
        "INSERT INTO sessions(id_hash, user_id, csrf_hash, created_at, last_seen_at, expires_at, user_agent) "
        "VALUES (:h, :u, :c, :t, :t, :x, :ua)",
        h=id_hash,
        u=uid,
        c=csrf_hash,
        t=t,
        x=_in(timedelta(days=days)),
        ua=ua[:200],
    )


def get_session(c: Connection, id_hash: str) -> dict[str, Any] | None:
    return one(
        c, "SELECT * FROM sessions WHERE id_hash = :h AND expires_at > :t", h=id_hash, t=now_iso()
    )


def touch_session(c: Connection, id_hash: str) -> None:
    ex(c, "UPDATE sessions SET last_seen_at = :t WHERE id_hash = :h", t=now_iso(), h=id_hash)


def delete_session(c: Connection, id_hash: str) -> None:
    ex(c, "DELETE FROM sessions WHERE id_hash = :h", h=id_hash)


def drop_unproven_password(c: Connection, uid: int) -> None:
    """Pre-account-hijacking guard: a password set on an account whose email was never confirmed
    may belong to someone else. Remove it (and every session) before the real owner takes over."""
    ex(c, "UPDATE users SET password_hash = NULL WHERE id = :i", i=uid)
    delete_user_sessions(c, uid)


def delete_user_sessions(c: Connection, uid: int, keep: str | None = None) -> None:
    ex(c, "DELETE FROM sessions WHERE user_id = :u AND id_hash != :k", u=uid, k=keep or "")


# ---- email tokens ---------------------------------------------------------------------------


def create_email_token(
    c: Connection,
    token_hash: str,
    purpose: str,
    email: str,
    uid: int | None,
    hours: int,
    org_id: int | None = None,
) -> None:
    ex(
        c,
        "INSERT INTO email_tokens(token_hash, user_id, purpose, email, org_id, created_at, expires_at) "
        "VALUES (:h, :u, :p, :e, :o, :t, :x)",
        h=token_hash,
        u=uid,
        p=purpose,
        e=email.lower(),
        o=org_id,
        t=now_iso(),
        x=_in(timedelta(hours=hours)),
    )


def use_email_token(c: Connection, token_hash: str, purpose: str) -> dict[str, Any] | None:
    row = one(
        c,
        "SELECT * FROM email_tokens WHERE token_hash = :h AND purpose = :p AND used_at IS NULL "
        "AND expires_at > :t",
        h=token_hash,
        p=purpose,
        t=now_iso(),
    )
    if row:
        ex(
            c,
            "UPDATE email_tokens SET used_at = :t WHERE token_hash = :h",
            t=now_iso(),
            h=token_hash,
        )
    return row


def pending_invites(c: Connection, email: str) -> list[dict[str, Any]]:
    return q(
        c,
        "SELECT * FROM email_tokens WHERE purpose = 'invite' AND email = :e AND used_at IS NULL "
        "AND expires_at > :t",
        e=email.lower(),
        t=now_iso(),
    )


# ---- orgs, members --------------------------------------------------------------------------


def create_org(c: Connection, name: str, slug: str) -> int:
    return insert(
        c,
        "INSERT INTO orgs(name, slug, created_at) VALUES (:n, :s, :t)",
        n=name[:120],
        s=slug,
        t=now_iso(),
    )


def slug_taken(c: Connection, slug: str) -> bool:
    return one(c, "SELECT id FROM orgs WHERE slug = :s", s=slug) is not None


def add_member(c: Connection, org_id: int, uid: int, role: str) -> None:
    if one(c, "SELECT 1 AS x FROM memberships WHERE org_id = :o AND user_id = :u", o=org_id, u=uid):
        return
    ex(
        c,
        "INSERT INTO memberships(org_id, user_id, role, created_at) VALUES (:o, :u, :r, :t)",
        o=org_id,
        u=uid,
        r=role,
        t=now_iso(),
    )


def memberships(c: Connection, uid: int) -> list[dict[str, Any]]:
    return q(
        c,
        "SELECT o.*, m.role FROM memberships m JOIN orgs o ON o.id = m.org_id WHERE m.user_id = :u "
        "ORDER BY o.id",
        u=uid,
    )


def members(c: Connection, org_id: int) -> list[dict[str, Any]]:
    return q(
        c,
        "SELECT u.id, u.email, u.name, m.role, m.created_at FROM memberships m JOIN users u "
        "ON u.id = m.user_id WHERE m.org_id = :o ORDER BY m.created_at",
        o=org_id,
    )


def member_count(c: Connection, org_id: int) -> int:
    r = one(c, "SELECT COUNT(*) AS n FROM memberships WHERE org_id = :o", o=org_id)
    return int(r["n"]) if r else 0


def remove_member(c: Connection, org_id: int, uid: int) -> None:
    ex(
        c,
        "DELETE FROM memberships WHERE org_id = :o AND user_id = :u AND role != 'owner'",
        o=org_id,
        u=uid,
    )


def set_role(c: Connection, org_id: int, uid: int, role: str) -> None:
    ex(
        c,
        "UPDATE memberships SET role = :r WHERE org_id = :o AND user_id = :u AND role != 'owner'",
        r=role,
        o=org_id,
        u=uid,
    )


def org(c: Connection, org_id: int) -> dict[str, Any] | None:
    return one(c, "SELECT * FROM orgs WHERE id = :o", o=org_id)


def set_plan(c: Connection, org_id: int, plan_id: str, billing_ref: str | None) -> None:
    ex(
        c,
        "UPDATE orgs SET plan = :p, billing_ref = COALESCE(:b, billing_ref) WHERE id = :o",
        p=plan_id,
        b=billing_ref,
        o=org_id,
    )


def apply_billing_event(
    c: Connection, org_id: int, plan_id: str, billing_ref: str | None, event_time: str
) -> bool:
    """Set the plan from a provider event unless a newer event was already applied (D-025).
    Returns False for stale or replayed events. ISO 8601 UTC strings compare in time order."""
    row = one(c, "SELECT billing_updated_at FROM orgs WHERE id = :o", o=org_id)
    if row is None:
        return False
    last = row["billing_updated_at"]
    if last and event_time and event_time <= last:
        return False
    ex(
        c,
        "UPDATE orgs SET plan = :p, billing_ref = COALESCE(:b, billing_ref), "
        "billing_updated_at = :t WHERE id = :o",
        p=plan_id,
        b=billing_ref,
        t=event_time or None,
        o=org_id,
    )
    return True


def rename_org(c: Connection, org_id: int, name: str) -> None:
    ex(c, "UPDATE orgs SET name = :n WHERE id = :o", n=name[:120], o=org_id)


# ---- projects, keys -------------------------------------------------------------------------


def create_project(c: Connection, org_id: int, name: str, slug: str, repo_url: str) -> int:
    return insert(
        c,
        "INSERT INTO projects(org_id, name, slug, repo_url, created_at) VALUES (:o, :n, :s, :r, :t)",
        o=org_id,
        n=name[:120],
        s=slug,
        r=repo_url[:300],
        t=now_iso(),
    )


def projects(c: Connection, org_id: int) -> list[dict[str, Any]]:
    return q(
        c,
        "SELECT p.*, (SELECT COUNT(*) FROM issues i WHERE i.project_id = p.id AND i.status IN "
        "('open','reopened','triaged')) AS open_issues, (SELECT COUNT(*) FROM case_files f WHERE "
        "f.project_id = p.id) AS case_files FROM projects p WHERE p.org_id = :o ORDER BY p.id",
        o=org_id,
    )


def project(c: Connection, org_id: int, pid: int) -> dict[str, Any] | None:
    return one(c, "SELECT * FROM projects WHERE id = :p AND org_id = :o", p=pid, o=org_id)


def project_count(c: Connection, org_id: int) -> int:
    r = one(c, "SELECT COUNT(*) AS n FROM projects WHERE org_id = :o", o=org_id)
    return int(r["n"]) if r else 0


def project_slug_taken(c: Connection, org_id: int, slug: str) -> bool:
    return (
        one(c, "SELECT id FROM projects WHERE org_id = :o AND slug = :s", o=org_id, s=slug)
        is not None
    )


def update_project(c: Connection, pid: int, name: str, repo_url: str) -> None:
    ex(
        c,
        "UPDATE projects SET name = :n, repo_url = :r WHERE id = :p",
        n=name[:120],
        r=repo_url[:300],
        p=pid,
    )


def delete_project(c: Connection, pid: int) -> None:
    ex(c, "DELETE FROM projects WHERE id = :p", p=pid)


def create_key(c: Connection, pid: int, name: str, prefix: str, key_hash: str, uid: int) -> int:
    return insert(
        c,
        "INSERT INTO api_keys(project_id, name, prefix, key_hash, created_by, created_at) "
        "VALUES (:p, :n, :x, :h, :u, :t)",
        p=pid,
        n=name[:80],
        x=prefix,
        h=key_hash,
        u=uid,
        t=now_iso(),
    )


def keys(c: Connection, pid: int) -> list[dict[str, Any]]:
    return q(
        c,
        "SELECT id, name, prefix, created_at, last_used_at, revoked_at FROM api_keys WHERE project_id = :p "
        "ORDER BY id DESC",
        p=pid,
    )


def revoke_key(c: Connection, pid: int, kid: int) -> int:
    return ex(
        c,
        "UPDATE api_keys SET revoked_at = :t WHERE id = :k AND project_id = :p AND revoked_at IS NULL",
        t=now_iso(),
        k=kid,
        p=pid,
    )


def key_lookup(c: Connection, key_hash: str) -> dict[str, Any] | None:
    row = one(
        c,
        "SELECT k.id AS key_id, k.project_id, p.org_id, p.name AS project_name, p.slug AS project_slug, "
        "o.plan, o.name AS org_name FROM api_keys k JOIN projects p ON p.id = k.project_id JOIN orgs o "
        "ON o.id = p.org_id WHERE k.key_hash = :h AND k.revoked_at IS NULL",
        h=key_hash,
    )
    if row:
        ex(c, "UPDATE api_keys SET last_used_at = :t WHERE id = :k", t=now_iso(), k=row["key_id"])
    return row


# ---- usage ----------------------------------------------------------------------------------


def period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def usage(c: Connection, org_id: int) -> dict[str, int]:
    r = one(
        c,
        "SELECT events, dropped FROM usage_counters WHERE org_id = :o AND period = :p",
        o=org_id,
        p=period(),
    )
    return {"events": int(r["events"]) if r else 0, "dropped": int(r["dropped"]) if r else 0}


def count_event(c: Connection, org_id: int, dropped: bool) -> None:
    p = period()
    if (
        one(c, "SELECT 1 AS x FROM usage_counters WHERE org_id = :o AND period = :p", o=org_id, p=p)
        is None
    ):
        ex(
            c,
            "INSERT INTO usage_counters(org_id, period, events, dropped) VALUES (:o, :p, 0, 0)",
            o=org_id,
            p=p,
        )
    sql = (
        "UPDATE usage_counters SET dropped = dropped + 1 WHERE org_id = :o AND period = :p"
        if dropped
        else "UPDATE usage_counters SET events = events + 1 WHERE org_id = :o AND period = :p"
    )
    ex(c, sql, o=org_id, p=p)


# ---- issues (production errors) -------------------------------------------------------------


def upsert_issue(
    c: Connection,
    pid: int,
    fingerprint: str,
    title: str,
    exc_type: str | None,
    environment: str,
    release: str,
    at: str,
) -> tuple[int, bool]:
    row = one(
        c,
        "SELECT id, status FROM issues WHERE project_id = :p AND fingerprint = :f",
        p=pid,
        f=fingerprint,
    )
    if row:
        status = "reopened" if row["status"] == "resolved" else row["status"]
        ex(
            c,
            "UPDATE issues SET event_count = event_count + 1, last_seen_at = :t, status = :s, "
            "environment = :e, last_release = :r WHERE id = :i",
            t=at,
            s=status,
            e=environment[:60],
            r=release[:80],
            i=row["id"],
        )
        return int(row["id"]), False
    iid = insert(
        c,
        "INSERT INTO issues(project_id, fingerprint, title, exception_type, environment, last_release, "
        "first_seen_at, last_seen_at) VALUES (:p, :f, :ti, :x, :e, :r, :t, :t)",
        p=pid,
        f=fingerprint,
        ti=title[:300],
        x=exc_type,
        e=environment[:60],
        r=release[:80],
        t=at,
    )
    return iid, True


def add_issue_event(c: Connection, iid: int, pid: int, payload: dict[str, Any]) -> None:
    ex(
        c,
        "INSERT INTO issue_events(issue_id, project_id, received_at, payload_json) VALUES (:i, :p, :t, :j)",
        i=iid,
        p=pid,
        t=now_iso(),
        j=json.dumps(payload)[:200_000],
    )


def issues(c: Connection, pid: int, status: str | None, limit: int = 100) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, fingerprint, title, exception_type, status, environment, last_release, first_seen_at, "
        "last_seen_at, event_count, triage_json IS NOT NULL AS triaged FROM issues WHERE project_id = :p"
    )
    if status:
        sql += " AND status = :s"
    return q(c, sql + " ORDER BY last_seen_at DESC LIMIT :l", p=pid, s=status, l=limit)


def issue(c: Connection, pid: int, iid: int) -> dict[str, Any] | None:
    return one(c, "SELECT * FROM issues WHERE id = :i AND project_id = :p", i=iid, p=pid)


def issue_events(c: Connection, iid: int, limit: int = 20) -> list[dict[str, Any]]:
    rows = q(
        c,
        "SELECT id, received_at, payload_json FROM issue_events WHERE issue_id = :i ORDER BY id DESC "
        "LIMIT :l",
        i=iid,
        l=limit,
    )
    return [
        {"id": r["id"], "received_at": r["received_at"], "payload": json.loads(r["payload_json"])}
        for r in rows
    ]


def set_issue_status(c: Connection, iid: int, status: str) -> None:
    ex(c, "UPDATE issues SET status = :s WHERE id = :i", s=status, i=iid)


def set_triage(c: Connection, iid: int, triage: dict[str, Any]) -> None:
    ex(
        c,
        "UPDATE issues SET triage_json = :j, status = CASE WHEN status IN ('open','reopened') THEN 'triaged' "
        "ELSE status END WHERE id = :i",
        j=json.dumps(triage),
        i=iid,
    )


# ---- case files (synced from the local CLI) -------------------------------------------------


def upsert_case_file(
    c: Connection,
    pid: int,
    local_id: int,
    title: str,
    status: str,
    certainty: str | None,
    payload: dict[str, Any],
) -> None:
    t = now_iso()
    data = json.dumps(payload)[:1_000_000]
    if one(
        c,
        "SELECT id FROM case_files WHERE project_id = :p AND local_incident_id = :l",
        p=pid,
        l=local_id,
    ):
        ex(
            c,
            "UPDATE case_files SET title = :ti, status = :s, top_certainty = :c, payload_json = :j, updated_at = :t "
            "WHERE project_id = :p AND local_incident_id = :l",
            ti=title[:300],
            s=status,
            c=certainty,
            j=data,
            t=t,
            p=pid,
            l=local_id,
        )
        return
    ex(
        c,
        "INSERT INTO case_files(project_id, local_incident_id, title, status, top_certainty, payload_json, "
        "received_at, updated_at) VALUES (:p, :l, :ti, :s, :c, :j, :t, :t)",
        p=pid,
        l=local_id,
        ti=title[:300],
        s=status,
        c=certainty,
        j=data,
        t=t,
    )


def case_files(c: Connection, pid: int) -> list[dict[str, Any]]:
    return q(
        c,
        "SELECT id, local_incident_id, title, status, top_certainty, received_at, updated_at FROM case_files "
        "WHERE project_id = :p ORDER BY updated_at DESC LIMIT 200",
        p=pid,
    )


def case_file(c: Connection, pid: int, cid: int) -> dict[str, Any] | None:
    row = one(c, "SELECT * FROM case_files WHERE id = :i AND project_id = :p", i=cid, p=pid)
    if row:
        row["payload"] = json.loads(row.pop("payload_json"))
    return row


# ---- billing, audit, retention --------------------------------------------------------------


def upgrade_request(c: Connection, org_id: int, uid: int, plan_id: str) -> None:
    ex(
        c,
        "INSERT INTO upgrade_requests(org_id, user_id, plan, created_at) VALUES (:o, :u, :p, :t)",
        o=org_id,
        u=uid,
        p=plan_id,
        t=now_iso(),
    )


def audit(
    c: Connection, org_id: int | None, uid: int | None, action: str, detail: str = ""
) -> None:
    ex(
        c,
        "INSERT INTO audit_log(org_id, user_id, action, detail, at) VALUES (:o, :u, :a, :d, :t)",
        o=org_id,
        u=uid,
        a=action,
        d=detail[:500],
        t=now_iso(),
    )


def audit_entries(c: Connection, org_id: int, limit: int = 50) -> list[dict[str, Any]]:
    return q(
        c,
        "SELECT a.action, a.detail, a.at, u.email FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
        "WHERE a.org_id = :o ORDER BY a.id DESC LIMIT :l",
        o=org_id,
        l=limit,
    )


def apply_retention(c: Connection, org_id: int, days: int) -> int:
    """Data retention by plan (03_DATA-RULES). Runtime data lifecycle, not a schema change."""
    cutoff = _in(timedelta(days=-days))
    return ex(
        c,
        "DELETE FROM issue_events WHERE received_at < :c AND project_id IN "
        "(SELECT id FROM projects WHERE org_id = :o)",
        c=cutoff,
        o=org_id,
    )


def all_orgs(c: Connection) -> list[dict[str, Any]]:
    return q(c, "SELECT id, plan FROM orgs")


def expire_sessions(c: Connection) -> int:
    return ex(c, "DELETE FROM sessions WHERE expires_at < :t", t=now_iso())

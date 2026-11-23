"""Signed-in app API: account, workspace, members, projects, API keys, issues, case files, plan."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from faultsage.cloud import mailer, plans, security
from faultsage.cloud.deps import Ctx, clear_session_cookies, current, rate_limit
from faultsage.cloud.routes.auth import EMAIL, slugify
from faultsage.cloud.settings import get_settings
from faultsage.cloud.storage import repo
from faultsage.cloud.storage.db import tx
from faultsage.cloud.triage_agent import triage
from faultsage.errors import (
    ForbiddenError,
    NotFoundError,
    PlanLimitError,
    UnauthorisedError,
    ValidationFailedError,
)

router = APIRouter(prefix="/api/v1", tags=["app"])
C = Depends(current)


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    repo_url: str = Field(default="", max_length=300)


class KeyBody(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=80)


class InviteBody(BaseModel):
    email: str = Field(max_length=254)


class RoleBody(BaseModel):
    role: Literal["viewer", "maintainer"]


class StatusBody(BaseModel):
    status: Literal["open", "triaged", "fix_in_review", "resolved", "ignored"]


class ConfirmBody(BaseModel):
    confirm: str = Field(max_length=300)
    password: str = Field(default="", max_length=256)


class UpgradeBody(BaseModel):
    plan: Literal["pro"] = "pro"


def _public_user(u: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u["name"],
        "email_verified": bool(u["email_verified_at"]),
        "has_password": bool(u["password_hash"]),
        "github_linked": bool(u["github_id"]),
        "created_at": u["created_at"],
    }


def _project(ctx: Ctx, pid: int) -> dict[str, Any]:
    with tx() as c:
        p = repo.project(c, ctx.org["id"], pid)
    if p is None:
        raise NotFoundError("Project not found in this workspace.", "")
    return p


@router.get("/me")
def me(ctx: Ctx = C) -> dict[str, Any]:
    p = plans.plan(ctx.org["plan"])
    with tx() as c:
        use = repo.usage(c, ctx.org["id"])
        n_projects = repo.project_count(c, ctx.org["id"])
        n_members = repo.member_count(c, ctx.org["id"])
    return {
        "user": _public_user(ctx.user),
        "org": {
            "id": ctx.org["id"],
            "name": ctx.org["name"],
            "slug": ctx.org["slug"],
            "role": ctx.role,
            "plan": p.as_dict(),
        },
        "orgs": [{"id": o["id"], "name": o["name"], "role": o["role"]} for o in ctx.orgs],
        "usage": {**use, "projects": n_projects, "members": n_members},
    }


@router.put("/me")
def update_me(body: NameBody, ctx: Ctx = C) -> dict[str, Any]:
    with tx() as c:
        repo.update_name(c, ctx.user["id"], body.name.strip())
    return {"ok": True}


@router.post("/me/delete")
def delete_me(body: ConfirmBody, response: Response, ctx: Ctx = C) -> dict[str, Any]:
    if body.confirm.strip().lower() != f"delete {ctx.user['email']}":
        raise ValidationFailedError(
            f"Type exactly: delete {ctx.user['email']}", "Nothing was deleted."
        )
    if ctx.user["password_hash"] and not security.verify_password(
        ctx.user["password_hash"], body.password
    ):
        raise UnauthorisedError("Password is wrong. Nothing was deleted.", "")
    with tx() as c:
        repo.audit(c, None, ctx.user["id"], "account.deleted")
        repo.delete_user(c, ctx.user["id"])
    clear_session_cookies(response)
    return {"ok": True}


@router.put("/org")
def rename_org(body: NameBody, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("owner")
    with tx() as c:
        repo.rename_org(c, ctx.org["id"], body.name.strip())
        repo.audit(c, ctx.org["id"], ctx.user["id"], "org.renamed", body.name)
    return {"ok": True}


@router.get("/org/members")
def members(ctx: Ctx = C) -> list[dict[str, Any]]:
    with tx() as c:
        return repo.members(c, ctx.org["id"])


@router.post("/org/members/invite")
def invite(body: InviteBody, request: Request, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("owner")
    rate_limit(request, "invite", 20, 3600, str(ctx.org["id"]))
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise ValidationFailedError("Enter a valid email address.", "")
    if not ctx.user["email_verified_at"]:
        raise ForbiddenError(
            "Confirm your own email before inviting others.", "Use the link we sent you."
        )
    p = plans.plan(ctx.org["plan"])
    with tx() as c:
        if repo.member_count(c, ctx.org["id"]) >= p.seats:
            raise PlanLimitError(
                f"The {p.name} plan has {p.seats} seat(s).", "Upgrade to add members."
            )
        existing = repo.user_by_email(c, email)
        if existing:
            repo.add_member(c, ctx.org["id"], existing["id"], "viewer")
            repo.audit(c, ctx.org["id"], ctx.user["id"], "member.added", email)
            link = f"{get_settings().base_url}/login"
        else:
            link = ""
            token = security.new_token()
            repo.create_email_token(
                c, security.sha256(token), "invite", email, None, 24 * 7, ctx.org["id"]
            )
            repo.audit(c, ctx.org["id"], ctx.user["id"], "member.invited", email)
    # Same reply and an email either way, so the form never reveals who has an account.
    mailer.invite(
        email,
        ctx.org["name"],
        link or f"{get_settings().base_url}/signup?{urlencode({'email': email})}",
    )
    return {"invited": True}


@router.put("/org/members/{uid}")
def set_role(uid: int, body: RoleBody, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("owner")
    with tx() as c:
        repo.set_role(c, ctx.org["id"], uid, body.role)
        repo.audit(c, ctx.org["id"], ctx.user["id"], "member.role", f"{uid}={body.role}")
    return {"ok": True}


@router.delete("/org/members/{uid}")
def remove_member(uid: int, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("owner")
    with tx() as c:
        repo.remove_member(c, ctx.org["id"], uid)
        repo.audit(c, ctx.org["id"], ctx.user["id"], "member.removed", str(uid))
    return {"ok": True}


@router.get("/org/audit")
def audit(ctx: Ctx = C) -> list[dict[str, Any]]:
    ctx.require("maintainer")
    with tx() as c:
        return repo.audit_entries(c, ctx.org["id"])


# ---- projects ---------------------------------------------------------------------------------


@router.get("/projects")
def list_projects(ctx: Ctx = C) -> list[dict[str, Any]]:
    with tx() as c:
        return repo.projects(c, ctx.org["id"])


@router.post("/projects", status_code=201)
def create_project(body: ProjectBody, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("maintainer")
    p = plans.plan(ctx.org["plan"])
    repo_url = body.repo_url.strip()
    if repo_url and not repo_url.startswith("https://"):
        raise ValidationFailedError("Repository URL must start with https://", "")
    with tx() as c:
        if repo.project_count(c, ctx.org["id"]) >= p.projects:
            raise PlanLimitError(
                f"The {p.name} plan allows {p.projects} projects.", "Upgrade, or delete a project."
            )
        slug = slugify(body.name)
        base, n = slug, 2
        while repo.project_slug_taken(c, ctx.org["id"], slug):
            slug, n = f"{base}-{n}", n + 1
        pid = repo.create_project(c, ctx.org["id"], body.name.strip(), slug, repo_url)
        repo.audit(c, ctx.org["id"], ctx.user["id"], "project.created", body.name)
    return {"id": pid, "slug": slug}


@router.get("/projects/{pid}")
def get_project(pid: int, ctx: Ctx = C) -> dict[str, Any]:
    return _project(ctx, pid)


@router.put("/projects/{pid}")
def update_project(pid: int, body: ProjectBody, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("maintainer")
    _project(ctx, pid)
    if body.repo_url and not body.repo_url.startswith("https://"):
        raise ValidationFailedError("Repository URL must start with https://", "")
    with tx() as c:
        repo.update_project(c, pid, body.name.strip(), body.repo_url.strip())
    return {"ok": True}


@router.post("/projects/{pid}/delete")
def delete_project(pid: int, body: ConfirmBody, ctx: Ctx = C) -> dict[str, Any]:
    """Deleting a project deletes its issues, events, case files and keys. Typed confirmation."""
    ctx.require("owner")
    p = _project(ctx, pid)
    if body.confirm.strip() != f"delete {p['slug']}":
        raise ValidationFailedError(f"Type exactly: delete {p['slug']}", "Nothing was deleted.")
    with tx() as c:
        repo.delete_project(c, pid)
        repo.audit(c, ctx.org["id"], ctx.user["id"], "project.deleted", p["slug"])
    return {"ok": True}


@router.get("/projects/{pid}/keys")
def list_keys(pid: int, ctx: Ctx = C) -> list[dict[str, Any]]:
    ctx.require("maintainer")
    _project(ctx, pid)
    with tx() as c:
        return repo.keys(c, pid)


@router.post("/projects/{pid}/keys", status_code=201)
def create_key(pid: int, body: KeyBody, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("maintainer")
    _project(ctx, pid)
    raw, prefix, h = security.new_api_key()
    with tx() as c:
        kid = repo.create_key(c, pid, body.name, prefix, h, ctx.user["id"])
        repo.audit(c, ctx.org["id"], ctx.user["id"], "key.created", prefix)
    return {
        "id": kid,
        "key": raw,
        "prefix": prefix,
        "note": "Copy this key now. It is shown only once.",
    }


@router.delete("/projects/{pid}/keys/{kid}")
def revoke_key(pid: int, kid: int, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("maintainer")
    _project(ctx, pid)
    with tx() as c:
        n = repo.revoke_key(c, pid, kid)
        repo.audit(c, ctx.org["id"], ctx.user["id"], "key.revoked", str(kid))
    if not n:
        raise NotFoundError("Key not found or already revoked.", "")
    return {"ok": True}


# ---- issues (production errors) -------------------------------------------------------------


@router.get("/projects/{pid}/issues")
def list_issues(pid: int, status: str | None = None, ctx: Ctx = C) -> list[dict[str, Any]]:
    _project(ctx, pid)
    with tx() as c:
        rows = repo.issues(c, pid, status)
    for r in rows:
        r["triaged"] = bool(r["triaged"])
    return rows


@router.get("/projects/{pid}/issues/{iid}")
def get_issue(pid: int, iid: int, ctx: Ctx = C) -> dict[str, Any]:
    _project(ctx, pid)
    with tx() as c:
        issue = repo.issue(c, pid, iid)
        if issue is None:
            raise NotFoundError("Issue not found.", "")
        events = repo.issue_events(c, iid, 10)
    issue["triage"] = json.loads(issue.pop("triage_json")) if issue.get("triage_json") else None
    return {**issue, "events": events}


@router.put("/projects/{pid}/issues/{iid}/status")
def issue_status(pid: int, iid: int, body: StatusBody, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("maintainer")
    _project(ctx, pid)
    with tx() as c:
        if repo.issue(c, pid, iid) is None:
            raise NotFoundError("Issue not found.", "")
        repo.set_issue_status(c, iid, body.status)
        repo.audit(c, ctx.org["id"], ctx.user["id"], "issue.status", f"FS-{iid}={body.status}")
    return {"ok": True}


@router.post("/projects/{pid}/issues/{iid}/triage")
def run_triage(pid: int, iid: int, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("maintainer")
    project = _project(ctx, pid)
    with tx() as c:
        issue = repo.issue(c, pid, iid)
        if issue is None:
            raise NotFoundError("Issue not found.", "")
        result = triage(issue, repo.issue_events(c, iid, 20), project)
        repo.set_triage(c, iid, result)
    return result


# ---- case files (from the local CLI) ----------------------------------------------------------


@router.get("/projects/{pid}/case-files")
def list_case_files(pid: int, ctx: Ctx = C) -> list[dict[str, Any]]:
    _project(ctx, pid)
    with tx() as c:
        return repo.case_files(c, pid)


@router.get("/projects/{pid}/case-files/{cid}")
def get_case_file(pid: int, cid: int, ctx: Ctx = C) -> dict[str, Any]:
    _project(ctx, pid)
    with tx() as c:
        cf = repo.case_file(c, pid, cid)
    if cf is None:
        raise NotFoundError("Case file not found.", "")
    return cf


# ---- plan and billing -------------------------------------------------------------------------


@router.post("/billing/upgrade")
def upgrade(body: UpgradeBody, ctx: Ctx = C) -> dict[str, Any]:
    ctx.require("owner")
    s = get_settings()
    with tx() as c:
        repo.upgrade_request(c, ctx.org["id"], ctx.user["id"], body.plan)
        repo.audit(c, ctx.org["id"], ctx.user["id"], "billing.upgrade_requested", body.plan)
    if s.billing_enabled:
        query = urlencode(
            {"checkout[custom][org_id]": str(ctx.org["id"]), "checkout[email]": ctx.user["email"]}
        )
        url = f"{s.lemonsqueezy_checkout_url}?{query}"
        return {"checkout_url": url}
    return {
        "checkout_url": None,
        "message": "Paid plans are not open yet. We saved your request and will email "
        "you when Pro is available. Everything in Free keeps working.",
    }


# Lemon Squeezy subscription statuses. "cancelled" means cancelled but paid until the period ends
# (the refund policy promises access until then); "expired", "unpaid" and "paused" end Pro.
PAID_STATUSES = frozenset({"active", "on_trial", "past_due", "cancelled"})


def normalise_time(value: str) -> str:
    """Provider timestamps to one ISO 8601 UTC form so they compare as text."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@router.post("/billing/webhook/lemonsqueezy", include_in_schema=False)
async def lemonsqueezy_webhook(request: Request) -> dict[str, Any]:
    """Billing adapter (Q-004). Verifies the HMAC signature before trusting anything."""
    s = get_settings()
    body = await request.body()
    sig = request.headers.get("x-signature", "")
    if not s.lemonsqueezy_webhook_secret:
        raise ForbiddenError("Billing is not configured.", "")
    expected = hmac.new(s.lemonsqueezy_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ForbiddenError("Bad signature.", "")
    try:
        data = json.loads(body)
    except ValueError as e:
        raise ValidationFailedError("Body is not JSON.", "") from e
    meta = data.get("meta") or {}
    event = str(meta.get("event_name", ""))
    org_raw = (meta.get("custom_data") or {}).get("org_id")
    obj = data.get("data") or {}
    attrs = obj.get("attributes") or {}
    # Only events that carry a subscription object decide the plan. Orders and payment events
    # (subscription_payment_* carry an invoice whose status is "paid") are ignored, so they can
    # never downgrade anyone.
    if (
        not event.startswith("subscription_")
        or obj.get("type") != "subscriptions"
        or not str(org_raw or "").isdigit()
    ):
        return {"ignored": True}
    org_id = int(str(org_raw))
    status = str(attrs.get("status", ""))
    plan_id = "pro" if status in PAID_STATUSES else "free"
    event_time = normalise_time(str(attrs.get("updated_at") or ""))
    with tx() as c:
        applied = repo.apply_billing_event(
            c, org_id, plan_id, str(obj.get("id", "")) or None, event_time
        )
        if applied:
            repo.audit(c, org_id, None, "billing.plan", f"{event}:{status}->{plan_id}")
    if not applied:
        return {"ignored": True, "reason": "stale or unknown organisation"}
    return {"ok": True}

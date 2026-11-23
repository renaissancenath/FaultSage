"""Sign up, sign in, sign out, email verification, password reset, GitHub OAuth."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from faultsage.cloud import mailer, security
from faultsage.cloud.deps import (
    Ctx,
    clear_session_cookies,
    cookie_names,
    current,
    rate_limit,
    start_session,
)
from faultsage.cloud.settings import get_settings
from faultsage.cloud.storage import repo
from faultsage.cloud.storage.db import tx
from faultsage.errors import ForbiddenError, UnauthorisedError, ValidationFailedError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")
GENERIC = "Email or password is wrong."


class SignupBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    name: str = Field(default="", max_length=120)
    workspace: str = Field(default="", max_length=120)
    invite: str | None = Field(default=None, max_length=200)


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class EmailBody(BaseModel):
    email: str = Field(max_length=254)


class TokenBody(BaseModel):
    token: str = Field(max_length=200)


class ResetBody(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return s or "workspace"


def unique_slug(c: Any, base: str) -> str:
    slug = base
    while repo.slug_taken(c, slug):
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


def _send_verification(c: Any, uid: int, email: str) -> None:
    token = security.new_token()
    repo.create_email_token(c, security.sha256(token), "verify", email, uid, 24)
    mailer.verification(email, f"{get_settings().base_url}/verify-email#token={token}")


def _join_invites(c: Any, uid: int, email: str) -> bool:
    joined = False
    for inv in repo.pending_invites(c, email):
        if inv["org_id"]:
            repo.add_member(c, inv["org_id"], uid, "viewer")
            repo.use_email_token(c, inv["token_hash"], "invite")
            repo.audit(c, inv["org_id"], uid, "member.joined", email)
            joined = True
    return joined


def _new_account(
    c: Any,
    email: str,
    name: str,
    pw_hash: str | None,
    github_id: str | None,
    verified: bool,
    workspace: str,
) -> int:
    uid = repo.create_user(c, email, name, pw_hash, github_id, verified)
    joined = _join_invites(c, uid, email)
    if not joined or workspace:
        ws_name = workspace or (f"{name}'s workspace" if name else email.split("@")[0])
        oid = repo.create_org(c, ws_name, unique_slug(c, slugify(ws_name)))
        repo.add_member(c, oid, uid, "owner")
        repo.audit(c, oid, uid, "account.created", "github" if github_id else "email")
    return uid


@router.post("/signup", status_code=201)
def signup(body: SignupBody, request: Request, response: Response) -> dict[str, Any]:
    rate_limit(request, "signup", 5, 3600)
    s = get_settings()
    if not s.allow_signup:
        raise ForbiddenError("Sign up is closed on this server.", "Ask the operator for an invite.")
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise ValidationFailedError("Enter a valid email address.", "")
    problem = security.password_problem(body.password, email)
    if problem:
        raise ValidationFailedError(problem, "")
    with tx() as c:
        if repo.user_by_email(c, email):
            # Do not reveal whether the address is registered.
            raise ValidationFailedError(
                "Could not create an account with that email. If it is yours, sign in "
                "or reset the password.",
                "",
            )
        uid = _new_account(
            c,
            email,
            body.name.strip(),
            security.hash_password(body.password),
            None,
            False,
            body.workspace.strip(),
        )
        _send_verification(c, uid, email)
    start_session(response, request, uid)
    return {"ok": True, "verification_sent": s.smtp_enabled}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
    rate_limit(request, "login", 20, 300)
    rate_limit(request, "login-email", 10, 300, body.email.lower())
    email = body.email.strip().lower()
    # Errors are raised only after the transaction commits, so failure counts are kept.
    outcome = "ok"
    with tx() as c:
        user = repo.user_by_email(c, email)
        now = datetime.now(UTC)
        if (
            user
            and user["locked_until"]
            and datetime.fromisoformat(user["locked_until"].replace("Z", "+00:00")) > now
        ):
            security.verify_password(None, body.password)  # same timing
            outcome = "locked"
        elif (
            not security.verify_password(user["password_hash"] if user else None, body.password)
            or not user
        ):
            if user:
                until = security.lockout_until(user["failed_logins"] + 1)
                repo.record_login_failure(
                    c, user["id"], until.isoformat().replace("+00:00", "Z") if until else None
                )
            outcome = "wrong"
    if outcome == "locked":
        raise UnauthorisedError(
            "Too many failed attempts. Try again in a few minutes, or reset your password.", ""
        )
    if outcome == "wrong" or user is None:
        raise UnauthorisedError(GENERIC, "")
    with tx() as c:
        repo.reset_login_failures(c, user["id"])
        if security.needs_rehash(user["password_hash"]):
            repo.set_password(c, user["id"], security.hash_password(body.password))
        repo.audit(c, None, user["id"], "login", "password")
    start_session(response, request, user["id"])
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, ctx: Ctx = Depends(current)) -> dict[str, bool]:
    with tx() as c:
        repo.delete_session(c, ctx.session_hash)
    clear_session_cookies(response)
    return {"ok": True}


@router.post("/logout-everywhere")
def logout_all(response: Response, ctx: Ctx = Depends(current)) -> dict[str, bool]:
    with tx() as c:
        repo.delete_user_sessions(c, ctx.user["id"])
    clear_session_cookies(response)
    return {"ok": True}


@router.post("/verify-email")
def verify_email(body: TokenBody, request: Request) -> dict[str, bool]:
    rate_limit(request, "verify", 20, 3600)
    with tx() as c:
        row = repo.use_email_token(c, security.sha256(body.token), "verify")
        if row is None or row["user_id"] is None:
            raise ValidationFailedError(
                "This confirmation link has expired or was already used.",
                "Sign in and ask for a new link.",
            )
        repo.mark_verified(c, row["user_id"])
    return {"ok": True}


@router.post("/resend-verification")
def resend(request: Request, ctx: Ctx = Depends(current)) -> dict[str, bool]:
    rate_limit(request, "resend", 3, 3600, str(ctx.user["id"]))
    if ctx.user["email_verified_at"]:
        return {"ok": True}
    with tx() as c:
        _send_verification(c, ctx.user["id"], ctx.user["email"])
    return {"ok": True}


@router.post("/forgot-password")
def forgot(body: EmailBody, request: Request) -> dict[str, bool]:
    rate_limit(request, "forgot", 5, 3600)
    email = body.email.strip().lower()
    with tx() as c:
        user = repo.user_by_email(c, email)
        if user:
            token = security.new_token()
            repo.create_email_token(c, security.sha256(token), "reset", email, user["id"], 1)
            mailer.reset(email, f"{get_settings().base_url}/reset-password#token={token}")
    return {"ok": True}  # same answer whether or not the account exists


@router.post("/reset-password")
def reset_password(body: ResetBody, request: Request, response: Response) -> dict[str, bool]:
    rate_limit(request, "reset", 10, 3600)
    with tx() as c:
        row = repo.use_email_token(c, security.sha256(body.token), "reset")
        if row is None or row["user_id"] is None:
            raise ValidationFailedError(
                "This reset link has expired or was already used.", "Ask for a new link."
            )
        problem = security.password_problem(body.password, row["email"])
        if problem:
            raise ValidationFailedError(problem, "Ask for a new link and try again.")
        repo.set_password(c, row["user_id"], security.hash_password(body.password))
        repo.mark_verified(c, row["user_id"])  # they proved control of the inbox
        repo.delete_user_sessions(c, row["user_id"])
        repo.audit(c, None, row["user_id"], "password.reset")
    start_session(response, request, row["user_id"])
    return {"ok": True}


@router.post("/change-password")
def change_password(
    body: PasswordChange, request: Request, response: Response, ctx: Ctx = Depends(current)
) -> dict[str, bool]:
    rate_limit(request, "change-pw", 10, 3600, str(ctx.user["id"]))
    if ctx.user["password_hash"] and not security.verify_password(
        ctx.user["password_hash"], body.current_password
    ):
        raise UnauthorisedError("Current password is wrong.", "")
    problem = security.password_problem(body.new_password, ctx.user["email"])
    if problem:
        raise ValidationFailedError(problem, "")
    with tx() as c:
        repo.set_password(c, ctx.user["id"], security.hash_password(body.new_password))
        repo.delete_user_sessions(c, ctx.user["id"])
        repo.audit(c, ctx.org["id"], ctx.user["id"], "password.changed")
    start_session(response, request, ctx.user["id"])  # privilege change: rotate
    return {"ok": True}


# ---- GitHub OAuth (optional, free) -----------------------------------------------------------


@router.get("/github/start")
def github_start(request: Request) -> Response:
    s = get_settings()
    if not s.github_enabled:
        return RedirectResponse("/login?error=github_off", 303)
    rate_limit(request, "gh", 30, 300)
    state = security.new_token()
    url = (
        "https://github.com/login/oauth/authorize?"
        + httpx.QueryParams(
            {
                "client_id": s.github_client_id,
                "redirect_uri": f"{s.base_url}/api/v1/auth/github/callback",
                "scope": "read:user user:email",
                "state": state,
                "allow_signup": "true",
            }
        ).__str__()
    )
    resp = RedirectResponse(url, 303)
    resp.set_cookie(
        "fs_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=s.secure_cookies,
        samesite="lax",
        path="/api/v1/auth/github",
    )
    return resp


@router.get("/github/callback")
def github_callback(request: Request, code: str = "", state: str = "") -> Response:
    s = get_settings()
    expected = request.cookies.get("fs_oauth_state", "")
    if not s.github_enabled or not code or not expected or not security.same(expected, state):
        return RedirectResponse("/login?error=github_state", 303)
    try:
        tok = httpx.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": s.github_client_id,
                "client_secret": s.github_client_secret,
                "code": code,
                "redirect_uri": f"{s.base_url}/api/v1/auth/github/callback",
            },
            timeout=10,
        ).json()
        access = tok.get("access_token")
        if not access:
            return RedirectResponse("/login?error=github_denied", 303)
        h = {"Authorization": f"Bearer {access}", "Accept": "application/vnd.github+json"}
        gh_user = httpx.get("https://api.github.com/user", headers=h, timeout=10).json()
        emails = httpx.get("https://api.github.com/user/emails", headers=h, timeout=10).json()
    except (httpx.HTTPError, ValueError):
        return RedirectResponse("/login?error=github_unreachable", 303)
    primary = next(
        (
            e["email"]
            for e in emails
            if isinstance(e, dict) and e.get("primary") and e.get("verified")
        ),
        None,
    )
    gid = str(gh_user.get("id", ""))
    if not gid or not primary:
        return RedirectResponse("/login?error=github_email", 303)
    with tx() as c:
        user = repo.user_by_github(c, gid)
        if user is None:
            existing = repo.user_by_email(c, primary)
            if existing:
                if not existing["email_verified_at"]:
                    repo.drop_unproven_password(c, existing["id"])
                    repo.audit(c, None, existing["id"], "password.dropped_unverified")
                repo.link_github(c, existing["id"], gid)  # verified primary email at GitHub
                repo.mark_verified(c, existing["id"])
                uid = existing["id"]
            else:
                uid = _new_account(
                    c,
                    primary,
                    str(gh_user.get("name") or gh_user.get("login") or ""),
                    None,
                    gid,
                    True,
                    "",
                )
        else:
            uid = user["id"]
        repo.audit(c, None, uid, "login", "github")
    resp = RedirectResponse("/app", 303)
    start_session(resp, request, uid)
    resp.delete_cookie("fs_oauth_state", path="/api/v1/auth/github")
    return resp


def session_cookie_name() -> str:
    return cookie_names()[0]

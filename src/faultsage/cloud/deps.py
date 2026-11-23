"""Request dependencies: session user, CSRF, roles, API keys, client IP, rate limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response

from faultsage.cloud import security
from faultsage.cloud.settings import get_settings
from faultsage.cloud.storage import repo
from faultsage.cloud.storage.db import tx
from faultsage.errors import ForbiddenError, RateLimitedError, UnauthorisedError

ROLE_RANK = {"viewer": 0, "maintainer": 1, "owner": 2}
STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def cookie_names() -> tuple[str, str]:
    """__Host- prefix needs Secure, so it is used only over HTTPS."""
    if get_settings().secure_cookies:
        return "__Host-fs_session", "__Host-fs_csrf"
    return "fs_session", "fs_csrf"


def client_ip(request: Request) -> str:
    """The visitor's IP for rate limits. Behind a proxy, only the entries the proxies appended are
    trustworthy: the leftmost entries are whatever the visitor sent, so reading them would let
    anyone skip the rate limits by sending a fake X-Forwarded-For header."""
    s = get_settings()
    if s.trusted_proxy:
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",")]
        entries = [e for e in entries if e]
        if entries:
            return entries[max(0, len(entries) - s.proxy_hops)][:64]
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, bucket: str, limit: int, window_s: float, extra: str = "") -> None:
    key = f"{bucket}:{client_ip(request)}:{extra}"
    if not security.limiter.allow(key, limit, window_s):
        wait = security.limiter.wait_seconds(key, window_s)
        when = f"{wait} seconds" if wait < 90 else f"{(wait + 59) // 60} minutes"
        raise RateLimitedError(
            f"Too many attempts from your network. Try again in {when}.",
            "This limit protects accounts from automated attacks.",
        )


def set_session_cookies(response: Response, sid: str, csrf: str) -> None:
    s = get_settings()
    sess, csrf_name = cookie_names()
    max_age = security.SESSION_DAYS * 86400
    response.set_cookie(
        sess, sid, max_age=max_age, httponly=True, secure=s.secure_cookies, samesite="lax", path="/"
    )
    # Readable by our own JS so it can echo it in X-CSRF-Token (double submit).
    response.set_cookie(
        csrf_name,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=s.secure_cookies,
        samesite="strict",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    sess, csrf_name = cookie_names()
    s = get_settings()
    for n in (sess, csrf_name):
        response.delete_cookie(n, path="/", secure=s.secure_cookies)


def start_session(response: Response, request: Request, uid: int) -> None:
    """Rotate: a new id on every login (02_LOGIN-RULES section 4)."""
    sid, csrf = security.new_token(), security.new_token()
    old = request.cookies.get(cookie_names()[0])
    with tx() as c:
        if old:
            repo.delete_session(c, security.sha256(old))
        repo.create_session(
            c,
            security.sha256(sid),
            uid,
            security.sha256(csrf),
            security.SESSION_DAYS,
            request.headers.get("user-agent", ""),
        )
    set_session_cookies(response, sid, csrf)


@dataclass
class Ctx:
    user: dict[str, Any]
    session_hash: str
    org: dict[str, Any]
    role: str
    orgs: list[dict[str, Any]]

    def require(self, role: str) -> None:
        if ROLE_RANK[self.role] < ROLE_RANK[role]:
            raise ForbiddenError(
                f"This needs the {role} role in {self.org['name']}.", "Ask an owner."
            )


def current(request: Request) -> Ctx:
    sess_name, _ = cookie_names()
    sid = request.cookies.get(sess_name)
    if not sid:
        raise UnauthorisedError("You are not signed in.", "Sign in to continue.")
    h = security.sha256(sid)
    with tx() as c:
        sess = repo.get_session(c, h)
        if sess is None:
            raise UnauthorisedError("Your session has ended.", "Sign in again.")
        if request.method in STATE_CHANGING:
            token = request.headers.get("x-csrf-token", "")
            if not token or not security.same(security.sha256(token), sess["csrf_hash"]):
                raise ForbiddenError("Security token missing or wrong. Reload the page.", "")
        user = repo.user_by_id(c, sess["user_id"])
        if user is None:
            raise UnauthorisedError("Account not found.", "Sign in again.")
        repo.touch_session(c, h)
        orgs = repo.memberships(c, user["id"])
    if not orgs:
        raise ForbiddenError("Your account has no workspace.", "Contact support.")
    wanted = request.headers.get("x-org-id") or request.query_params.get("org")
    org = next((o for o in orgs if str(o["id"]) == wanted), orgs[0])
    return Ctx(user=user, session_hash=h, org=org, role=org["role"], orgs=orgs)


def api_key(request: Request) -> dict[str, Any]:
    auth = request.headers.get("authorization", "")
    raw = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not raw.startswith("fsk_"):
        raise UnauthorisedError(
            "Missing or malformed API key.", "Send Authorization: Bearer fsk_..."
        )
    rate_limit(request, "ingest", 600, 60, raw[:12])
    with tx() as c:
        key = repo.key_lookup(c, security.sha256(raw))
    if key is None:
        raise UnauthorisedError("API key not valid or revoked.", "Create a new key in Settings.")
    return key

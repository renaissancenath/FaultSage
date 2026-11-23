"""Sessions end when they should, and GitHub sign-in cannot be hijacked."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from faultsage.cloud.routes import auth as auth_routes
from faultsage.cloud.settings import get_settings
from tests.cloud.conftest import PASSWORD, signup


def _login(c: TestClient, email: str, password: str = PASSWORD) -> int:
    return c.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code


def _device(c: TestClient, cookies: dict[str, str] | None = None) -> TestClient:
    """Another browser on the same server (own cookie jar)."""
    d = TestClient(c.app, base_url="http://localhost:8000")
    for k, v in (cookies or {}).items():
        d.cookies.set(k, v)
    return d


def _signed_in_device(c: TestClient, email: str) -> TestClient:
    d = _device(c)
    assert _login(d, email) == 200
    return d


def _jar(c: TestClient) -> dict[str, str]:
    return {k.name: k.value or "" for k in c.cookies.jar}


def test_logout_everywhere_ends_other_devices(cloud: TestClient) -> None:
    h = signup(cloud, "ana@example.com")
    phone = _signed_in_device(cloud, "ana@example.com")
    assert phone.get("/api/v1/me").status_code == 200
    assert cloud.post("/api/v1/auth/logout-everywhere", headers=h).status_code == 200
    assert phone.get("/api/v1/me").status_code == 401
    assert cloud.get("/api/v1/me").status_code == 401


def test_password_change_ends_other_sessions_and_rotates_mine(cloud: TestClient) -> None:
    h = signup(cloud, "ana@example.com")
    old_session = _jar(cloud)
    phone = _signed_in_device(cloud, "ana@example.com")
    new = "a different long passphrase 42"
    r = cloud.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": new},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert phone.get("/api/v1/me").status_code == 401
    assert _device(cloud, old_session).get("/api/v1/me").status_code == 401
    assert cloud.get("/api/v1/me").status_code == 200  # the new, rotated session
    assert _login(_device(cloud), "ana@example.com") == 401
    assert _login(_device(cloud), "ana@example.com", new) == 200


def test_logout_needs_csrf(cloud: TestClient) -> None:
    signup(cloud, "ana@example.com")
    assert cloud.post("/api/v1/auth/logout").status_code == 403
    assert cloud.get("/api/v1/me").status_code == 200


class _Resp:
    def __init__(self, data: Any) -> None:
        self._d = data

    def json(self) -> Any:
        return self._d


@pytest.fixture
def github(cloud: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "secret")
    get_settings.cache_clear()

    def fake_post(url: str, **_: Any) -> _Resp:
        return _Resp({"access_token": "gho_test"})

    def fake_get(url: str, **_: Any) -> _Resp:
        if url.endswith("/user"):
            return _Resp({"id": 4242, "login": "victim"})
        return _Resp([{"email": "victim@example.com", "primary": True, "verified": True}])

    monkeypatch.setattr(auth_routes.httpx, "post", fake_post)
    monkeypatch.setattr(auth_routes.httpx, "get", fake_get)
    return cloud


def _github_sign_in(c: TestClient, state: str = "") -> Any:
    start = c.get("/api/v1/auth/github/start", follow_redirects=False)
    assert start.status_code == 303
    real = start.headers["location"].split("state=")[1].split("&")[0]
    return c.get(
        f"/api/v1/auth/github/callback?code=x&state={state or real}", follow_redirects=False
    )


def test_github_state_must_match(github: TestClient) -> None:
    r = _github_sign_in(github, state="forged")
    assert r.headers["location"] == "/login?error=github_state"
    assert github.get("/api/v1/me").status_code == 401


def test_github_sign_in_drops_a_squatters_password(github: TestClient) -> None:
    # Attacker registers the victim's email first and never confirms it.
    signup(github, "victim@example.com")
    squatter = _jar(github)
    github.cookies.clear()
    # The real owner signs in with GitHub, which has verified the email.
    r = _github_sign_in(github)
    assert r.headers["location"] == "/app"
    assert github.get("/api/v1/me").json()["user"]["email"] == "victim@example.com"
    # The attacker's session and password no longer work.
    assert _device(github, squatter).get("/api/v1/me").status_code == 401
    assert _login(_device(github), "victim@example.com") == 401


def test_github_sign_in_keeps_a_verified_owners_password(github: TestClient) -> None:
    signup(github, "victim@example.com")
    from faultsage.cloud.storage import repo
    from faultsage.cloud.storage.db import tx

    with tx() as c:
        uid = repo.user_by_email(c, "victim@example.com")["id"]  # type: ignore[index]
        repo.mark_verified(c, uid)
    github.cookies.clear()
    assert _github_sign_in(github).headers["location"] == "/app"
    assert _login(_device(github), "victim@example.com") == 200


def test_rate_limit_says_how_long_to_wait(cloud: TestClient) -> None:
    for i in range(5):
        r = cloud.post(
            "/api/v1/auth/signup", json={"email": f"u{i}@example.com", "password": PASSWORD}
        )
        assert r.status_code == 201
        cloud.cookies.clear()
    r = cloud.post("/api/v1/auth/signup", json={"email": "u9@example.com", "password": PASSWORD})
    assert r.status_code == 429
    assert "Try again in 60 minutes" in r.json()["error"]["message"]


def test_rate_limit_cannot_be_dodged_with_a_fake_forwarded_ip(
    cloud: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behind a proxy the visitor controls the left of X-Forwarded-For; only the right is real."""
    monkeypatch.setenv("FAULTSAGE_TRUSTED_PROXY", "true")
    get_settings.cache_clear()
    codes = []
    for i in range(7):
        r = cloud.post(
            "/api/v1/auth/forgot-password",
            json={"email": "x@example.com"},
            headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"},  # fake, then proxy-added
        )
        codes.append(r.status_code)
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    # A different real client (as added by the proxy) is not affected.
    r = cloud.post(
        "/api/v1/auth/forgot-password",
        json={"email": "x@example.com"},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert r.status_code == 200

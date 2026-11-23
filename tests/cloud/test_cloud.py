from __future__ import annotations

from fastapi.testclient import TestClient

from faultsage.cloud import mailer
from faultsage.cloud.plans import PLANS
from tests.cloud.conftest import PASSWORD, project_with_key, signup

TB = (
    'Traceback (most recent call last):\n  File "/srv/app/shop/views.py", line 42, in checkout\n'
    '    total = cart.total(user.discount)\n  File "/srv/app/shop/cart.py", line 17, in total\n'
    "    return 1\nAttributeError: 'NoneType' object has no attribute 'rate'\n"
)


def test_signup_rules(cloud: TestClient) -> None:
    assert (
        cloud.post(
            "/api/v1/auth/signup", json={"email": "a@example.com", "password": "short"}
        ).status_code
        == 422
    )
    r = cloud.post(
        "/api/v1/auth/signup", json={"email": "a@example.com", "password": "passwordpassword"}
    )
    assert r.status_code == 422 and "breach" in r.json()["error"]["message"]
    assert (
        cloud.post(
            "/api/v1/auth/signup", json={"email": "not-an-email", "password": PASSWORD}
        ).status_code
        == 422
    )
    signup(cloud, "a@example.com")
    cloud.cookies.clear()
    r = cloud.post("/api/v1/auth/signup", json={"email": "A@example.com", "password": PASSWORD})
    assert r.status_code == 422 and "Could not create" in r.json()["error"]["message"]


def test_session_cookie_flags_and_csrf(cloud: TestClient) -> None:
    signup(cloud)
    assert cloud.post("/api/v1/projects", json={"name": "x"}).status_code == 403
    assert (
        cloud.post(
            "/api/v1/projects", json={"name": "x"}, headers={"X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    me = cloud.get("/api/v1/me").json()
    assert me["org"]["plan"]["id"] == "free" and me["org"]["role"] == "owner"


def test_login_is_generic_and_locks_out(cloud: TestClient) -> None:
    h = signup(cloud)
    cloud.post("/api/v1/auth/logout", headers=h)
    unknown = cloud.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    wrong = cloud.post(
        "/api/v1/auth/login", json={"email": "ana@example.com", "password": "wrong password 1"}
    )
    assert (
        unknown.json()["error"]["message"]
        == wrong.json()["error"]["message"]
        == "Email or password is wrong."
    )
    for _ in range(5):
        r = cloud.post(
            "/api/v1/auth/login", json={"email": "ana@example.com", "password": "wrong password 1"}
        )
    assert "Too many" in r.json()["error"]["message"]
    r = cloud.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": PASSWORD})
    assert r.status_code == 401  # still locked even with the right password


def test_verify_and_reset_tokens_are_single_use(cloud: TestClient) -> None:
    signup(cloud)
    link = mailer.outbox[-1].get_content()
    token = link.split("#token=")[1].split()[0]
    assert cloud.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    assert cloud.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 422
    assert cloud.get("/api/v1/me").json()["user"]["email_verified"] is True
    cloud.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"})
    reset = mailer.outbox[-1].get_content().split("#token=")[1].split()[0]
    new = "a different long passphrase"
    assert (
        cloud.post(
            "/api/v1/auth/reset-password", json={"token": reset, "password": new}
        ).status_code
        == 200
    )
    assert (
        cloud.post(
            "/api/v1/auth/reset-password", json={"token": reset, "password": new}
        ).status_code
        == 422
    )
    cloud.cookies.clear()
    assert (
        cloud.post(
            "/api/v1/auth/login", json={"email": "ana@example.com", "password": new}
        ).status_code
        == 200
    )


def test_forgot_password_does_not_reveal_accounts(cloud: TestClient) -> None:
    r1 = cloud.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r1.status_code == 200 and r1.json() == {"ok": True}


def test_ingest_groups_triages_and_counts(cloud: TestClient) -> None:
    h = signup(cloud)
    pid, key = project_with_key(cloud, h)
    auth = {"Authorization": f"Bearer {key}"}
    for rel in ("1.0.0", "1.0.1"):
        r = cloud.post(
            "/api/v1/ingest/events",
            json={"traceback": TB, "release": rel, "message": "password=hunter2hunter2"},
            headers=auth,
        )
        assert r.status_code == 202
    issues = cloud.get(f"/api/v1/projects/{pid}/issues").json()
    assert len(issues) == 1 and issues[0]["event_count"] == 2
    detail = cloud.get(f"/api/v1/projects/{pid}/issues/{issues[0]['id']}").json()
    t = detail["triage"]
    assert t["location"]["file_path"] == "/srv/app/shop/cart.py" and t["location"]["line"] == 17
    assert (
        t["certainty"] in ("possible", "strong")
        and "github.com/acme/shop/issues/new" in t["github_issue_url"]
    )
    assert "hunter2" not in str(detail["events"])
    assert cloud.get("/api/v1/me").json()["usage"]["events"] == 2


def test_bad_or_revoked_keys_are_refused(cloud: TestClient) -> None:
    h = signup(cloud)
    pid, key = project_with_key(cloud, h)
    assert (
        cloud.get("/api/v1/ingest/whoami", headers={"Authorization": "Bearer fsk_nope"}).status_code
        == 401
    )
    kid = cloud.get(f"/api/v1/projects/{pid}/keys").json()[0]["id"]
    cloud.delete(f"/api/v1/projects/{pid}/keys/{kid}", headers=h)
    assert (
        cloud.get("/api/v1/ingest/whoami", headers={"Authorization": f"Bearer {key}"}).status_code
        == 401
    )


def test_plan_limits(cloud: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    h = signup(cloud)
    for i in range(PLANS["free"].projects):
        assert cloud.post("/api/v1/projects", json={"name": f"p{i}"}, headers=h).status_code == 201
    r = cloud.post("/api/v1/projects", json={"name": "one more"}, headers=h)
    assert r.status_code == 402 and r.json()["error"]["code"] == "plan_limit"
    from dataclasses import replace

    from faultsage.cloud import plans

    monkeypatch.setitem(plans.PLANS, "free", replace(PLANS["free"], events_per_month=1))
    key = cloud.post("/api/v1/projects/1/keys", json={}, headers=h).json()["key"]
    auth = {"Authorization": f"Bearer {key}"}
    assert (
        cloud.post("/api/v1/ingest/events", json={"traceback": TB}, headers=auth).status_code == 202
    )
    assert (
        cloud.post("/api/v1/ingest/events", json={"traceback": TB}, headers=auth).status_code == 402
    )
    assert cloud.get("/api/v1/me").json()["usage"]["dropped"] == 1


def test_tenant_isolation(cloud: TestClient) -> None:
    h = signup(cloud, "a@example.com")
    pid, _ = project_with_key(cloud, h)
    cloud.cookies.clear()
    signup(cloud, "b@example.com")
    assert cloud.get(f"/api/v1/projects/{pid}").status_code == 404
    assert cloud.get(f"/api/v1/projects/{pid}/issues").status_code == 404


def test_viewer_cannot_change_things(cloud: TestClient) -> None:
    h = signup(cloud, "owner@example.com")
    owner_cookies = dict(cloud.cookies)
    token = mailer.outbox[-1].get_content().split("#token=")[1].split()[0]
    cloud.post("/api/v1/auth/verify-email", json={"token": token})
    cloud.post("/api/v1/projects", json={"name": "p"}, headers=h)
    refused = cloud.post(
        "/api/v1/org/members/invite", json={"email": "viewer@example.com"}, headers=h
    )
    assert refused.status_code == 402  # Free has one seat
    from faultsage.cloud.storage import db, repo

    with db.tx() as c:
        repo.set_plan(c, 1, "pro", None)
    assert cloud.post(
        "/api/v1/org/members/invite", json={"email": "viewer@example.com"}, headers=h
    ).json() == {"invited": True}
    cloud.cookies.clear()
    r = cloud.post(
        "/api/v1/auth/signup", json={"email": "viewer@example.com", "password": PASSWORD}
    )
    hv = {"X-CSRF-Token": cloud.cookies.get("fs_csrf") or ""}
    me = cloud.get("/api/v1/me").json()
    assert r.status_code == 201 and me["org"]["role"] == "viewer" and me["org"]["name"] != "viewer"
    assert cloud.post("/api/v1/projects", json={"name": "nope"}, headers=hv).status_code == 403
    assert owner_cookies


def test_project_delete_needs_typed_confirmation(cloud: TestClient) -> None:
    h = signup(cloud)
    pid, _ = project_with_key(cloud, h)
    assert (
        cloud.post(f"/api/v1/projects/{pid}/delete", json={"confirm": "yes"}, headers=h).status_code
        == 422
    )
    assert (
        cloud.post(
            f"/api/v1/projects/{pid}/delete", json={"confirm": "delete shop"}, headers=h
        ).status_code
        == 200
    )
    assert cloud.get(f"/api/v1/projects/{pid}").status_code == 404


def test_account_deletion(cloud: TestClient) -> None:
    h = signup(cloud)
    assert (
        cloud.post(
            "/api/v1/me/delete",
            json={"confirm": "delete ana@example.com", "password": "wrong"},
            headers=h,
        ).status_code
        == 401
    )
    assert (
        cloud.post(
            "/api/v1/me/delete",
            json={"confirm": "delete ana@example.com", "password": PASSWORD},
            headers=h,
        ).status_code
        == 200
    )
    assert (
        cloud.post(
            "/api/v1/auth/login", json={"email": "ana@example.com", "password": PASSWORD}
        ).status_code
        == 401
    )


def test_case_file_upload_from_cli(cloud: TestClient) -> None:
    h = signup(cloud)
    pid, key = project_with_key(cloud, h)
    cf = {
        "incident_id": 3,
        "title": "test_fit failed: KeyError",
        "status": "open",
        "first_seen_at": "2026-11-23T03:00:00Z",
        "last_seen_at": "2026-11-23T03:00:00Z",
        "hypotheses": [
            {
                "rank": 1,
                "score": 0.9,
                "certainty": "strong",
                "claim": "clean.py:4 renamed the column",
            }
        ],
    }
    r = cloud.post(
        "/api/v1/ingest/case-files",
        json={"client": "t", "project": "p", "case_file": cf},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 202
    rows = cloud.get(f"/api/v1/projects/{pid}/case-files").json()
    assert rows[0]["top_certainty"] == "strong"


def test_upgrade_without_billing_records_interest(cloud: TestClient) -> None:
    h = signup(cloud)
    r = cloud.post("/api/v1/billing/upgrade", json={"plan": "pro"}, headers=h).json()
    assert r["checkout_url"] is None and "not open yet" in r["message"]


def test_headers_and_meta(cloud: TestClient) -> None:
    r = cloud.get("/api/v1/meta")
    assert r.json()["plans"][0]["id"] == "free"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert cloud.get("/healthz").json() == {"status": "ok"}


def test_case_files_never_store_source_code(cloud: TestClient) -> None:
    """D-030: even if a client sends code excerpts or patches, the server drops them."""
    h = signup(cloud)
    pid, key = project_with_key(cloud, h)
    cf = {
        "incident_id": 9,
        "title": "boom",
        "status": "open",
        "first_seen_at": "2026-11-23T03:00:00Z",
        "last_seen_at": "2026-11-23T03:00:00Z",
        "hypotheses": [
            {
                "rank": 1,
                "score": 0.5,
                "certainty": "possible",
                "claim": "x",
                "location": {
                    "file_path": "src/app.py",
                    "line": 3,
                    "excerpt": [[3, "SECRET_ALGORITHM = do_magic()"]],
                },
            }
        ],
        "suggestions": [{"explanation": "e", "patch_diff": "+SECRET_ALGORITHM = 2"}],
    }
    body = {"client": "t", "project": "p", "case_file": cf}
    auth = {"Authorization": f"Bearer {key}"}
    assert cloud.post("/api/v1/ingest/case-files", json=body, headers=auth).status_code == 202
    cid = cloud.get(f"/api/v1/projects/{pid}/case-files").json()[0]["id"]
    stored = cloud.get(f"/api/v1/projects/{pid}/case-files/{cid}").text
    assert "SECRET_ALGORITHM" not in stored
    assert "src/app.py" in stored  # the location itself is kept

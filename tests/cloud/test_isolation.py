"""Tenant isolation (D-026): a second customer calls every route that takes an id, using the first
customer's ids. Nothing may be read or changed. Adding a route with an id means adding it here."""

from __future__ import annotations

from fastapi.testclient import TestClient

from faultsage.cloud.app import create_app
from tests.cloud.conftest import project_with_key, signup
from tests.cloud.test_cloud import TB

CF = {
    "incident_id": 1,
    "title": "boom",
    "status": "open",
    "first_seen_at": "2026-11-23T03:00:00Z",
    "last_seen_at": "2026-11-23T03:00:00Z",
    "hypotheses": [],
}


def _victim(c: TestClient) -> dict[str, int | str]:
    h = signup(c, "victim@example.com")
    pid, key = project_with_key(c, h, "secret-project")
    auth = {"Authorization": f"Bearer {key}"}
    assert c.post("/api/v1/ingest/events", json={"traceback": TB}, headers=auth).status_code == 202
    body = {"client": "t", "project": "p", "case_file": CF}
    assert c.post("/api/v1/ingest/case-files", json=body, headers=auth).status_code == 202
    iid = c.get(f"/api/v1/projects/{pid}/issues").json()[0]["id"]
    cid = c.get(f"/api/v1/projects/{pid}/case-files").json()[0]["id"]
    kid = c.get(f"/api/v1/projects/{pid}/keys").json()[0]["id"]
    me = c.get("/api/v1/me").json()
    return {
        "pid": pid,
        "iid": iid,
        "cid": cid,
        "kid": kid,
        "key": key,
        "uid": me["user"]["id"],
        "org": me["org"]["id"],
    }


def _snapshot(c: TestClient, v: dict[str, int | str]) -> list[object]:
    pid = v["pid"]
    return [
        c.get(f"/api/v1/projects/{pid}").json(),
        # last_used_at moves when the test itself uses the victim's key on purpose
        [{**k, "last_used_at": None} for k in c.get(f"/api/v1/projects/{pid}/keys").json()],
        c.get(f"/api/v1/projects/{pid}/issues").json(),
        c.get(f"/api/v1/projects/{pid}/case-files").json(),
        c.get("/api/v1/org/members").json(),
        c.get("/api/v1/me").json()["org"],
    ]


def test_every_id_route_refuses_another_tenant(cloud: TestClient) -> None:
    v = _victim(cloud)
    before = _snapshot(cloud, v)
    victim = cloud
    cloud = TestClient(victim.app, base_url="http://localhost:8000")  # the attacker's browser
    h = signup(cloud, "attacker@example.com")
    pid, iid, cid, kid, uid = v["pid"], v["iid"], v["cid"], v["kid"], v["uid"]
    calls = [
        ("GET", f"/api/v1/projects/{pid}", None),
        ("PUT", f"/api/v1/projects/{pid}", {"name": "pwned"}),
        ("POST", f"/api/v1/projects/{pid}/delete", {"confirm": "secret-project"}),
        ("GET", f"/api/v1/projects/{pid}/keys", None),
        ("POST", f"/api/v1/projects/{pid}/keys", {"name": "mine"}),
        ("DELETE", f"/api/v1/projects/{pid}/keys/{kid}", None),
        ("GET", f"/api/v1/projects/{pid}/issues", None),
        ("GET", f"/api/v1/projects/{pid}/issues/{iid}", None),
        ("PUT", f"/api/v1/projects/{pid}/issues/{iid}/status", {"status": "ignored"}),
        ("POST", f"/api/v1/projects/{pid}/issues/{iid}/triage", None),
        ("GET", f"/api/v1/projects/{pid}/case-files", None),
        ("GET", f"/api/v1/projects/{pid}/case-files/{cid}", None),
    ]
    for method, url, body in calls:
        r = cloud.request(method, url, json=body, headers=h)
        assert r.status_code == 404, (method, url, r.status_code, r.text)
        assert "secret-project" not in r.text and "AttributeError" not in r.text

    # Id-in-path routes scoped to the caller's own org: they may answer ok, but must not touch
    # the victim's workspace (checked by the snapshot below).
    cloud.put(f"/api/v1/org/members/{uid}", json={"role": "viewer"}, headers=h)
    cloud.delete(f"/api/v1/org/members/{uid}", headers=h)

    # Choosing the victim's workspace with the org header or query falls back to the caller's own.
    forged = {**h, "X-Org-Id": str(v["org"])}
    assert cloud.get("/api/v1/me", headers=forged).json()["org"]["id"] != v["org"]
    assert cloud.get(f"/api/v1/projects/{pid}?org={v['org']}", headers=forged).status_code == 404
    assert cloud.get("/api/v1/projects", headers=forged).json() == []

    # A project's key only ever writes into that project, whoever holds it.
    own_pid, _ = project_with_key(cloud, h, "attacker-project")
    victim_key = {"Authorization": f"Bearer {v['key']}"}
    ev = {"traceback": TB, "release": "x"}
    assert cloud.post("/api/v1/ingest/events", json=ev, headers=victim_key).status_code == 202
    assert cloud.get(f"/api/v1/projects/{own_pid}/issues").json() == []
    before[2] = None  # the event above went to the victim's project; compare the rest

    after = _snapshot(victim, v)
    after[2] = None
    assert after == before


def test_api_key_cannot_read_dashboard_routes(cloud: TestClient) -> None:
    v = _victim(cloud)
    cloud.cookies.clear()
    auth = {"Authorization": f"Bearer {v['key']}"}
    for url in (
        f"/api/v1/projects/{v['pid']}",
        "/api/v1/me",
        f"/api/v1/projects/{v['pid']}/issues",
    ):
        assert cloud.get(url, headers=auth).status_code == 401, url


def test_isolation_list_covers_every_id_route() -> None:
    """Fails when someone adds a route with an id in its path without adding it above."""
    covered = {
        "/api/v1/projects/{pid}",
        "/api/v1/projects/{pid}/delete",
        "/api/v1/projects/{pid}/keys",
        "/api/v1/projects/{pid}/keys/{kid}",
        "/api/v1/projects/{pid}/issues",
        "/api/v1/projects/{pid}/issues/{iid}",
        "/api/v1/projects/{pid}/issues/{iid}/status",
        "/api/v1/projects/{pid}/issues/{iid}/triage",
        "/api/v1/projects/{pid}/case-files",
        "/api/v1/projects/{pid}/case-files/{cid}",
        "/api/v1/org/members/{uid}",
        "/{path:path}",
    }
    paths = {getattr(r, "path", "") for r in create_app().routes}
    with_ids = {p for p in paths if "{" in p}
    assert with_ids <= covered, with_ids - covered

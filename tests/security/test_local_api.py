"""SR-1 to SR-6, LR-1 to LR-8 against the real local app."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from faultsage.api.app import create_app
from faultsage.api.auth import SessionStore
from faultsage.config.loader import ProjectPaths
from faultsage.config.model import Config, DashboardCfg, ProjectCfg
from faultsage.daemon.service import Workspace
from tests.conftest import run_pytest

PORT = 8765
ORIGIN = f"http://127.0.0.1:{PORT}"


@pytest.fixture
def client(sample_project: Path) -> tuple[TestClient, SessionStore, str]:
    run_pytest(sample_project)
    ws = Workspace.open(ProjectPaths(sample_project))
    ws.ingest()
    sessions = SessionStore()
    token = sessions.new_token()
    return TestClient(create_app(ws, sessions, PORT), base_url=ORIGIN), sessions, token


def login(c: TestClient, token: str) -> None:
    r = c.post(
        "/auth/session",
        json={"token": token},
        headers={"Origin": ORIGIN, "X-FaultSage-Request": "1"},
    )
    assert r.status_code == 204
    assert (
        "httponly" in r.headers["set-cookie"].lower()
        and "samesite=strict" in r.headers["set-cookie"].lower()
    )


def test_config_refuses_non_loopback_bind() -> None:
    with pytest.raises(ValueError, match=r"127\.0\.0\.1"):
        DashboardCfg(host="0.0.0" + ".0")
    Config(project=ProjectCfg(name="x"))


def test_host_header_checked(client) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = client
    assert c.get("/api/meta", headers={"Host": "evil.example:8765"}).status_code == 421


def test_requires_session(client) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = client
    assert c.get("/api/incidents").status_code == 401


def test_token_is_one_time(client) -> None:  # type: ignore[no-untyped-def]
    c, _, token = client
    login(c, token)
    assert c.get("/api/incidents").status_code == 200
    c2 = TestClient(c.app, base_url=ORIGIN)
    r = c2.post(
        "/auth/session",
        json={"token": token},
        headers={"Origin": ORIGIN, "X-FaultSage-Request": "1"},
    )
    assert r.status_code == 401


def test_writes_need_origin_and_custom_header(client) -> None:  # type: ignore[no-untyped-def]
    c, _, token = client
    login(c, token)
    assert c.post("/api/scan").status_code == 403
    assert (
        c.post(
            "/api/scan", headers={"Origin": "https://evil.example", "X-FaultSage-Request": "1"}
        ).status_code
        == 403
    )
    assert c.post("/api/scan", headers={"Origin": ORIGIN}).status_code == 403
    assert (
        c.post("/api/scan", headers={"Origin": ORIGIN, "X-FaultSage-Request": "1"}).status_code
        == 202
    )


def test_security_headers_present(client) -> None:  # type: ignore[no-untyped-def]
    c, _, _ = client
    h = c.get("/api/meta").headers
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "script-src 'self'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff" and h["referrer-policy"] == "no-referrer"


def test_rate_limit_on_token_exchange() -> None:
    s = SessionStore()
    s.new_token()
    results = [s.exchange("wrong", now=100.0 + i) for i in range(11)]
    assert results == [None] * 11
    good = s.new_token()
    assert s.exchange(good, now=111.0) is None  # locked out for 60 s
    assert s.exchange(good, now=200.0) is not None


def test_max_five_sessions_and_revoke() -> None:
    s = SessionStore()
    sids = []
    for i in range(6):
        sids.append(s.exchange(s.new_token(), now=float(i * 61)))
    assert not s.valid(sids[0], now=400.0) and s.valid(sids[5], now=400.0)
    s.revoke_all()
    assert not s.valid(sids[5], now=401.0)


def test_purge_needs_typed_project_name(client) -> None:  # type: ignore[no-untyped-def]
    c, _, token = client
    login(c, token)
    h = {"Origin": ORIGIN, "X-FaultSage-Request": "1"}
    assert c.post("/api/purge", json={"confirm": "purge"}, headers=h).status_code == 422
    assert c.get("/api/incidents").json()["items"]


def test_approve_needs_explicit_confirm(client) -> None:  # type: ignore[no-untyped-def]
    c, _, token = client
    login(c, token)
    h = {"Origin": ORIGIN, "X-FaultSage-Request": "1"}
    assert (
        c.post("/api/suggestions/1/approve", json={"confirm": False}, headers=h).status_code == 422
    )


def test_errors_never_leak_stack_traces(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c, _, token = client
    login(c, token)
    from faultsage.daemon import service

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("internal detail /home/secret/path")

    monkeypatch.setattr(service.Workspace, "status", boom)
    quiet = TestClient(c.app, base_url=ORIGIN, raise_server_exceptions=False)
    quiet.cookies.update(c.cookies)
    r = quiet.get("/api/status")
    assert r.status_code == 500 and "secret" not in r.text and "Traceback" not in r.text


def test_no_network_during_runtime_commands(
    sample_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SR-6: ingest, analysis, scan and case files open no outbound connection."""
    real_connect = socket.socket.connect
    attempts: list[object] = []

    def guarded(self: socket.socket, address: object) -> object:
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "localhost", "::1") and not str(host).startswith("/"):
            attempts.append(address)
            raise OSError("network blocked by test")
        return real_connect(self, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guarded)
    run_pytest(sample_project)
    ws = Workspace.open(ProjectPaths(sample_project))
    ws.ingest()
    ws.case_file(1)
    ws.scan()
    assert attempts == []

"""Every local dashboard route against a real workspace on the sample project."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from faultsage.api.app import create_app
from faultsage.api.auth import SessionStore
from faultsage.config.loader import ProjectPaths
from faultsage.daemon.service import Workspace
from tests.conftest import needs_engine, run_pytest

ORIGIN = "http://127.0.0.1:8765"
W = {"Origin": ORIGIN, "X-FaultSage-Request": "1"}


@pytest.fixture
def api(sample_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    runs = tmp_path / "runs" / "2026-01-01_bugsinpy_test_1"
    runs.mkdir(parents=True)
    (runs / "run.json").write_text(
        json.dumps(
            {
                "run_id": runs.name,
                "dataset": "bugsinpy",
                "split": "test",
                "cases_attempted": 1,
                "cases_reproduced": 1,
            }
        )
    )
    (runs / "cases.jsonl").write_text('{"case_id": "x-1"}\nnot json\n')
    monkeypatch.setenv("FAULTSAGE_RESULTS", str(tmp_path / "runs"))
    run_pytest(sample_project)
    ws = Workspace.open(ProjectPaths(sample_project))
    ws.ingest()
    sessions = SessionStore()
    token = sessions.new_token()
    c = TestClient(create_app(ws, sessions, 8765), base_url=ORIGIN, raise_server_exceptions=False)
    assert c.post("/auth/session", json={"token": token}, headers=W).status_code == 204
    return c


def test_read_routes(api: TestClient) -> None:
    assert api.get("/api/meta").json()["mode"] == "local"
    st = api.get("/api/status").json()
    assert st["project"] == "churn" and st["open_incidents"] == 1
    items = api.get("/api/incidents?status=open_any&q=train").json()["items"]
    assert len(items) == 1
    assert api.get("/api/incidents?status=dismissed").json()["items"] == []
    cf = api.get("/api/incidents/1").json()
    assert cf["hypotheses"][0]["certainty"] == "possible"
    assert api.get("/api/incidents/99").status_code == 404
    md = api.get("/api/incidents/1/export?format=md")
    assert md.status_code == 200 and "I-1" in md.text
    assert api.get("/api/incidents/1/export?format=json").json()["incident_id"] == 1
    g = api.get("/api/graph?kind=imports&focus=1").json()
    assert any(n["on_failure_path"] for n in g["nodes"])
    assert api.get("/api/graph?kind=pipeline").json() == {"nodes": [], "edges": []}
    assert api.get("/api/pipeline").json()["declared"] is False
    assert api.get("/api/runs").json() == []
    assert api.get("/api/settings").json()["project"]["name"] == "churn"
    assert isinstance(api.get("/api/self-report").json(), list)
    assert api.get("/api/bench/runs").json()[0]["run_id"] == "2026-01-01_bugsinpy_test_1"
    assert api.get("/api/bench/runs/2026-01-01_bugsinpy_test_1").json()["cases"] == [
        {"case_id": "x-1"}
    ]
    assert api.get("/api/bench/runs/..%2Fetc").status_code == 404
    assert api.get("/api/nope").status_code == 404


@needs_engine
def test_write_routes(api: TestClient) -> None:
    assert api.post("/api/watch/pause", headers=W).json()["state"] == "paused"
    assert api.post("/api/incidents/1/verify", headers=W).status_code == 409  # paused
    assert api.post("/api/watch/resume", headers=W).json()["state"] == "running"
    assert api.post("/api/incidents/1/reanalyse", headers=W).json()["incident_id"] == 1
    scan = api.post("/api/scan", headers=W).json()
    assert api.get(f"/api/scan/{scan['id']}").status_code == 200
    assert api.get("/api/scan/latest").json()["id"] == scan["id"]
    assert api.get("/api/scan/999").status_code == 404
    assert api.post("/api/incidents/1/resolve", headers=W).status_code == 422  # not verified yet
    ap = api.post("/api/suggestions/1/approve", json={"confirm": True}, headers=W).json()
    assert ap["outcome"] == "applied"
    v = api.post("/api/incidents/1/verify", headers=W)
    assert v.status_code == 202
    vid = v.json()["id"]
    for _ in range(120):
        res = api.get(f"/api/verifications/{vid}").json()
        if res["result"]:
            break
        time.sleep(0.5)
    assert res["result"] == "resolved"
    assert api.get("/api/verifications/999").status_code == 404
    assert api.post("/api/incidents/1/resolve", headers=W).json()["status"] == "resolved"
    s = api.put(
        "/api/settings",
        json={
            "signals": {"git": False, "evil": True},
            "retention_days": 7,
            "port": 9000,
            "blast_radius_depth": 3,
            "coverage_contexts": True,
            "cloud_enabled": False,
        },
        headers=W,
    ).json()
    assert (
        s["signals"]["git"] is False
        and "evil" not in s["signals"]
        and s["restart_required"] is True
    )
    assert api.post("/api/incidents/1/dismiss", headers=W).json()["status"] == "dismissed"
    assert api.post("/api/purge", json={"confirm": "purge churn"}, headers=W).status_code == 204
    assert api.post("/api/watch/stop", headers=W).status_code == 204
    assert api.get("/api/status").status_code == 401  # sessions revoked on stop (LR-6)


def test_websocket_requires_origin_and_session(api: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect),
        api.websocket_connect("/ws/events", headers={"Origin": "https://evil.example"}) as ws,
    ):
        ws.receive_json()
    # Starlette's test client does not attach its cookie jar to websocket upgrades; browsers do.
    cookie = f"fs_session={api.cookies.get('fs_session')}"
    with (
        pytest.raises(WebSocketDisconnect),
        api.websocket_connect(
            "/ws/events", headers={"Origin": ORIGIN, "Cookie": "fs_session=wrong"}
        ) as ws_bad,
    ):
        ws_bad.receive_json()
    with api.websocket_connect("/ws/events", headers={"Origin": ORIGIN, "Cookie": cookie}) as ws:
        api.post("/api/watch/pause", headers=W)
        api.app.state.ws.emit("status.changed", {"state": "paused"})
        assert ws.receive_json()["type"] == "status.changed"

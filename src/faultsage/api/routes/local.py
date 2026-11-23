"""Local HTTP API routes (BACKEND_SCHEMA.md section 4). Routes call Workspace service methods."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from faultsage.api.auth import SESSION_COOKIE, SessionStore
from faultsage.bench.records import get_run, list_runs
from faultsage.config.loader import save
from faultsage.config.model import Config
from faultsage.daemon.service import Workspace
from faultsage.errors import (
    DaemonPausedError,
    NotFoundError,
    UnauthorisedError,
    ValidationFailedError,
)
from faultsage.export import to_markdown
from faultsage.models.core import Approval, CaseFile, Graph, IncidentSummary, Verification
from faultsage.storage import repo_events, repo_incidents


class ApproveBody(BaseModel):
    confirm: bool = Field(description="Must be true: the user saw the full diff (LR-8).")
    stash_confirmed: bool = False


class PurgeBody(BaseModel):
    confirm: str


class SettingsBody(BaseModel):
    signals: dict[str, Any] | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    port: int | None = Field(default=None, ge=1024, le=65535)
    blast_radius_depth: int | None = Field(default=None, ge=1, le=12)
    coverage_contexts: bool | None = None
    cloud_enabled: bool | None = None


class IncidentPage(BaseModel):
    items: list[IncidentSummary]
    next_cursor: int | None


def build_router(sessions: SessionStore, on_stop: Any = None) -> APIRouter:
    def require_session(request: Request) -> Workspace:
        if not sessions.valid(request.cookies.get(SESSION_COOKIE)):
            raise UnauthorisedError(
                "Not signed in to this dashboard.", "Run faultsage dashboard to open a new link."
            )
        ws: Workspace = request.app.state.ws
        return ws

    r = APIRouter(prefix="/api")
    session_ws = Depends(require_session)

    @r.get("/status")
    def status(ws: Workspace = session_ws) -> dict[str, Any]:
        return ws.status()

    @r.post("/watch/pause")
    def pause(ws: Workspace = session_ws) -> dict[str, Any]:
        ws.paths.control.write_text("pause", encoding="utf-8")
        ws.state = "paused"
        return ws.status()

    @r.post("/watch/resume")
    def resume(ws: Workspace = session_ws) -> dict[str, Any]:
        ws.paths.control.write_text("resume", encoding="utf-8")
        ws.state = "running"
        return ws.status()

    @r.post("/watch/stop", status_code=204)
    def stop(ws: Workspace = session_ws) -> Response:
        ws.paths.control.write_text("stop", encoding="utf-8")
        sessions.revoke_all()  # LR-6
        if on_stop:
            on_stop()
        return Response(status_code=204)

    @r.get("/incidents", response_model=IncidentPage)
    def incidents(
        ws: Workspace = session_ws,
        status: str | None = None,
        q: str | None = Query(None, max_length=200),
        limit: int = Query(50, ge=1, le=200),
        cursor: int | None = None,
    ) -> IncidentPage:
        items, nxt = ws.list_incidents(status, q, limit, cursor)
        return IncidentPage(items=items, next_cursor=nxt)

    @r.get("/incidents/{incident_id}", response_model=CaseFile)
    def incident(incident_id: int, ws: Workspace = session_ws) -> CaseFile:
        return ws.case_file(incident_id)

    @r.post("/incidents/{incident_id}/dismiss", response_model=IncidentSummary)
    def dismiss(incident_id: int, ws: Workspace = session_ws) -> IncidentSummary:
        return ws.set_incident_status(incident_id, "dismissed")

    @r.post("/incidents/{incident_id}/resolve", response_model=IncidentSummary)
    def resolve(incident_id: int, ws: Workspace = session_ws) -> IncidentSummary:
        cf = ws.case_file(incident_id)
        if cf.status != "verified":
            raise ValidationFailedError(
                "Only verified incidents can be marked resolved.", "Run verification first."
            )
        return ws.set_incident_status(incident_id, "resolved")

    @r.post("/incidents/{incident_id}/reanalyse", response_model=CaseFile)
    def reanalyse(incident_id: int, ws: Workspace = session_ws) -> CaseFile:
        with ws.lock:
            ws.analyse_incident(incident_id)
        return ws.case_file(incident_id)

    @r.get("/incidents/{incident_id}/export")
    def export(
        incident_id: int, format: Literal["md", "json"] = "md", ws: Workspace = session_ws
    ) -> Response:
        cf = ws.case_file(incident_id)
        if format == "json":
            return Response(
                cf.model_dump_json(indent=2),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="I-{incident_id}.json"'},
            )
        return PlainTextResponse(
            to_markdown(cf, ws.cfg.project.name),
            headers={"Content-Disposition": f'attachment; filename="I-{incident_id}.md"'},
        )

    @r.get("/graph", response_model=Graph)
    def graph(
        kind: Literal["imports", "pipeline"] = "imports",
        focus: int | None = None,
        ws: Workspace = session_ws,
    ) -> Graph:
        return ws.graph(kind, focus)

    @r.post("/suggestions/{suggestion_id}/approve", response_model=Approval)
    def approve(suggestion_id: int, body: ApproveBody, ws: Workspace = session_ws) -> Approval:
        if not body.confirm:
            raise ValidationFailedError(
                "Approval needs explicit confirmation.", "Confirm in the dialog."
            )
        with ws.lock:
            return ws.approve(suggestion_id, "dashboard", body.stash_confirmed)

    @r.post("/incidents/{incident_id}/verify", response_model=Verification, status_code=202)
    def verify(incident_id: int, ws: Workspace = session_ws) -> Verification:
        if ws.state == "paused":
            raise DaemonPausedError("Watching is paused.", "Resume watching, then verify.")
        return ws.verify(incident_id)

    @r.get("/verifications/{verification_id}", response_model=Verification)
    def verification(verification_id: int, ws: Workspace = session_ws) -> Verification:
        v = repo_incidents.get_verification(ws.conn, verification_id)
        if v is None:
            raise NotFoundError(f"Verification V-{verification_id} not found.")
        return v

    @r.post("/scan", status_code=202)
    def scan(ws: Workspace = session_ws) -> dict[str, Any]:
        sid = ws.scan()
        return repo_events.get_scan(ws.conn, sid) or {}

    @r.get("/scan/latest")
    def scan_latest(ws: Workspace = session_ws) -> dict[str, Any] | None:
        sid = repo_events.latest_scan_id(ws.conn, ws.project_id)
        return repo_events.get_scan(ws.conn, sid) if sid else None

    @r.get("/scan/{scan_id}")
    def scan_get(scan_id: int, ws: Workspace = session_ws) -> dict[str, Any]:
        s = repo_events.get_scan(ws.conn, scan_id)
        if s is None:
            raise NotFoundError(f"Scan {scan_id} not found.")
        return s

    @r.get("/pipeline")
    def pipeline(ws: Workspace = session_ws) -> dict[str, Any]:
        return ws.pipeline()

    @r.get("/runs")
    def runs(ws: Workspace = session_ws) -> list[dict[str, Any]]:
        out = []
        for row in repo_events.recent_events(ws.conn, ws.project_id, "run_result", 5):
            p = json.loads(row["payload_json"])
            out.append(
                {
                    "at": row["occurred_at"],
                    "command": " ".join(p.get("argv", [])),
                    "exit_code": p.get("exit_code"),
                }
            )
        return out

    @r.get("/bench/runs")
    def bench_runs(_: Workspace = session_ws) -> list[dict[str, Any]]:
        return list_runs()

    @r.get("/bench/runs/{run_id}")
    def bench_run(run_id: str, _: Workspace = session_ws) -> dict[str, Any]:
        run = get_run(run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found in results/runs.")
        return run

    @r.get("/settings")
    def settings(ws: Workspace = session_ws) -> dict[str, Any]:
        return ws.cfg.model_dump(mode="json")

    @r.put("/settings")
    def put_settings(body: SettingsBody, ws: Workspace = session_ws) -> dict[str, Any]:
        data = ws.cfg.model_dump(mode="json")
        restart = False
        if body.signals:
            allowed = {"pytest", "run_wrapper", "git", "file_watch"}
            for k, v in body.signals.items():
                if k in allowed and isinstance(v, bool):
                    data["signals"][k] = v
        if body.retention_days is not None:
            data["retention"]["event_days"] = body.retention_days
        if body.port is not None and body.port != data["dashboard"]["port"]:
            data["dashboard"]["port"] = body.port
            restart = True
        if body.blast_radius_depth is not None:
            data["analysis"]["blast_radius_depth"] = body.blast_radius_depth
        if body.coverage_contexts is not None:
            data["analysis"]["coverage_contexts"] = body.coverage_contexts
        if body.cloud_enabled is not None:
            data["cloud"]["enabled"] = body.cloud_enabled
        cfg = Config.model_validate(data)
        save(ws.paths, cfg, force=True)
        ws.cfg = cfg
        return {**cfg.model_dump(mode="json"), "restart_required": restart}

    @r.post("/purge", status_code=204)
    def purge(body: PurgeBody, ws: Workspace = session_ws) -> Response:
        expected = f"purge {ws.cfg.project.name}"  # SR-27
        if body.confirm.strip() != expected:
            raise ValidationFailedError(f"Type exactly: {expected}", "Nothing was deleted.")
        with ws.lock:
            ws.purge()
        return Response(status_code=204)

    @r.get("/self-report")
    def self_report(_: Workspace = session_ws) -> list[dict[str, Any]]:
        from faultsage.selfmon.hook import grouped

        return [{k: v for k, v in g.items() if k != "sample"} for g in grouped()]

    return r

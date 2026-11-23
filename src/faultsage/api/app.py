"""Local dashboard app: FastAPI on 127.0.0.1 (FR-27 to FR-30). Serves the prebuilt React app."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.telemetry import TelemetryConfig

from faultsage import __version__
from faultsage.api.auth import SESSION_COOKIE, SessionStore, allowed_origins
from faultsage.api.routes.local import build_router
from faultsage.api.security import local_guard
from faultsage.daemon.service import Workspace
from faultsage.errors import FaultSageError
from faultsage.selfmon import hook as selfmon

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "app"
# FastAPI >= 0.16x ships native OpenTelemetry. Turn it off: no runtime network calls (SR-6).
NO_TELEMETRY: TelemetryConfig = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "auto_configure": False,
    "operation_spans": False,
}


class Hub:
    """Fan-out of daemon events to WebSocket clients (FR-29)."""

    def __init__(self) -> None:
        self.queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def publish(self, event: dict[str, Any]) -> None:
        if self.loop is None:
            return
        for q in list(self.queues):
            self.loop.call_soon_threadsafe(q.put_nowait, event)


def static_response(path: str) -> Response:
    if not STATIC_DIR.exists():
        return JSONResponse(
            {
                "error": {
                    "code": "not_found",
                    "message": "Dashboard build not found.",
                    "next_step": "Run npm run build in web/ (see README).",
                }
            },
            404,
        )
    target = (STATIC_DIR / path).resolve()
    if path and target.is_file() and target.is_relative_to(STATIC_DIR.resolve()):
        return FileResponse(target)
    return FileResponse(STATIC_DIR / "index.html")


def create_app(ws: Workspace, sessions: SessionStore, port: int, on_stop: Any = None) -> FastAPI:
    app = FastAPI(
        title="FaultSage local",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        telemetry=NO_TELEMETRY,
    )
    hub = Hub()
    ws.listeners.append(hub.publish)
    app.state.ws = ws
    app.state.sessions = sessions
    app.state.port = port
    app.middleware("http")(local_guard(lambda: app.state.port))

    @app.exception_handler(FaultSageError)
    async def _fs_error(_: Request, exc: FaultSageError) -> JSONResponse:
        return JSONResponse(exc.as_dict(), status_code=exc.status)

    @app.exception_handler(Exception)
    async def _internal(_: Request, exc: Exception) -> JSONResponse:
        selfmon.record(exc, "api")  # SR-18: no trace in the response
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "Something failed inside FaultSage.",
                    "next_step": "Run faultsage self-report for details.",
                }
            },
            500,
        )

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        return {"mode": "local", "version": __version__}

    @app.post("/auth/session", status_code=204)
    async def auth_session(request: Request) -> Response:
        try:
            body = json.loads(await request.body() or b"{}")
        except ValueError:
            body = {}
        token = str(body.get("token", ""))[:200]
        sid = sessions.exchange(token)
        if sid is None:
            return JSONResponse(
                {
                    "error": {
                        "code": "unauthorised",
                        "message": "That dashboard link has expired or was already used.",
                        "next_step": "Run faultsage dashboard to get a new link.",
                    }
                },
                401,
            )
        resp = Response(status_code=204)
        resp.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="strict", path="/")
        return resp

    @app.post("/auth/logout", status_code=204)
    def logout() -> Response:
        sessions.revoke_all()
        resp = Response(status_code=204)
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

    app.include_router(build_router(sessions, on_stop))

    @app.websocket("/ws/events")
    async def events(socket: WebSocket) -> None:
        if socket.headers.get("origin") not in allowed_origins(
            app.state.port
        ) or not sessions.valid(socket.cookies.get(SESSION_COOKIE)):
            await socket.close(code=1008)
            return
        await socket.accept()
        hub.loop = asyncio.get_running_loop()
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        hub.queues.add(q)
        try:
            while True:
                event = await q.get()
                await socket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.queues.discard(q)

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith(("api/", "auth/", "ws/")):
            return JSONResponse(
                {"error": {"code": "not_found", "message": "No such route.", "next_step": ""}}, 404
            )
        return static_response(path)

    return app

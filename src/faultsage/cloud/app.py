"""FaultSage Cloud: one FastAPI app serving the API and the built React app (D-018)."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.telemetry import TelemetryConfig

from faultsage import __version__
from faultsage.api.security import SECURITY_HEADERS, csp
from faultsage.cloud import plans
from faultsage.cloud.routes import auth, ingest, workspace
from faultsage.cloud.settings import get_settings
from faultsage.cloud.storage import repo
from faultsage.cloud.storage.db import migrate_safe_on_start, tx
from faultsage.errors import FaultSageError
from faultsage.selfmon import hook as selfmon

_log = logging.getLogger("faultsage.cloud")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "app"
NO_TELEMETRY: TelemetryConfig = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "auto_configure": False,
    "operation_spans": False,
}
MAX_BODY = 2 * 1024 * 1024


def _housekeeping(stop: threading.Event) -> None:
    """Hourly: plan retention for production events, expired sessions."""
    while not stop.wait(3600):
        try:
            with tx() as c:
                for o in repo.all_orgs(c):
                    repo.apply_retention(c, o["id"], plans.plan(o["plan"]).retention_days)
                repo.expire_sessions(c)
        except Exception as e:
            selfmon.record(e, "cloud.housekeeping")


def create_app() -> FastAPI:
    s = get_settings()
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        blocked = migrate_safe_on_start()
        if blocked:
            m = blocked[0]
            msg = (
                f"Destructive migration {m.version:04d}_{m.name} is pending. It never runs on start. "
                f"Review it, then run: faultsage-cloud db migrate --approve {m.version} --env {s.environment} "
                "--approved-by <your name>"
            )
            if s.is_production:
                raise RuntimeError(msg)
            _log.warning(msg)
        if not s.smtp_enabled:
            _log.warning(
                "SMTP is not configured: verification and reset links are written to this log."
            )
        t = threading.Thread(target=_housekeeping, args=(stop,), daemon=True)
        t.start()
        yield
        stop.set()

    app = FastAPI(
        title="FaultSage Cloud",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if s.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if s.is_production else "/api/openapi.json",
        telemetry=NO_TELEMETRY,
    )

    @app.middleware("http")
    async def headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY:
            return JSONResponse(
                {
                    "error": {
                        "code": "validation_failed",
                        "message": "Request too large.",
                        "next_step": "",
                    }
                },
                413,
            )
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = csp("")
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v
        if s.secure_cookies:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(FaultSageError)
    async def _fs(_: Request, exc: FaultSageError) -> JSONResponse:
        return JSONResponse(exc.as_dict(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "request"
        return JSONResponse(
            {
                "error": {
                    "code": "validation_failed",
                    "message": f"{field}: {first.get('msg', 'invalid')}",
                    "next_step": "",
                }
            },
            422,
        )

    @app.exception_handler(Exception)
    async def _internal(_: Request, exc: Exception) -> JSONResponse:
        selfmon.record(exc, "cloud.api")
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "Something failed on our side.",
                    "next_step": "Try again. If it keeps happening, contact support.",
                }
            },
            500,
        )

    @app.get("/healthz", include_in_schema=False)
    def health() -> dict[str, str]:
        with tx() as c:
            c.exec_driver_sql("SELECT 1")
        return {"status": "ok"}

    @app.get("/api/v1/meta")
    def meta() -> dict[str, Any]:
        return {
            "mode": "cloud",
            "version": __version__,
            "github_login": s.github_enabled,
            "signup_open": s.allow_signup,
            "billing": s.billing_enabled,
            "email": s.smtp_enabled,
            "support_email": s.support_email,
            "legal": {
                "operator_name": s.operator_name,
                "operator_address": s.operator_address,
                "grievance_officer": s.grievance_officer,
                "grievance_email": s.grievance_email or s.support_email,
                "jurisdiction_city": s.jurisdiction_city,
                "hosting_region": s.hosting_region,
            },
            "plans": [p.as_dict() for p in plans.PLANS.values()],
        }

    app.include_router(auth.router)
    app.include_router(workspace.router)
    app.include_router(ingest.router)

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith("api/"):
            return JSONResponse(
                {"error": {"code": "not_found", "message": "No such route.", "next_step": ""}}, 404
            )
        if not STATIC_DIR.exists():
            return JSONResponse(
                {
                    "error": {
                        "code": "not_found",
                        "message": "Web app not built.",
                        "next_step": "Run npm run build in web/.",
                    }
                },
                404,
            )
        target = (STATIC_DIR / path).resolve()
        if path and target.is_file() and target.is_relative_to(STATIC_DIR.resolve()):
            resp: Response = FileResponse(target)
            if path.startswith("assets/"):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
        return FileResponse(STATIC_DIR / "index.html")

    return app

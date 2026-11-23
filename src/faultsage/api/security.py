"""Middleware shared by the local dashboard: Host and Origin checks, security headers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from faultsage.api.auth import allowed_hosts, allowed_origins

STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def csp(connect: str) -> str:
    # style-src-attr 'unsafe-inline' allows inline style ATTRIBUTES only (React Flow positions
    # nodes with them). <style> elements and all scripts stay 'self'. Decision D-020.
    return (
        "default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; "
        "img-src 'self' data:; "
        f"font-src 'self'; connect-src 'self' {connect}; frame-ancestors 'none'; base-uri 'none'; "
        "form-action 'self'"
    )


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def _err(status: int, code: str, message: str, next_step: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "next_step": next_step}}, status_code=status
    )


def local_guard(
    port_getter: Callable[[], int],
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        port = port_getter()
        host = request.headers.get("host", "")
        if host not in allowed_hosts(port):  # SR-2 DNS rebinding defence
            return _err(
                421,
                "forbidden_origin",
                "Unexpected Host header.",
                "Open the dashboard at 127.0.0.1.",
            )
        if request.method in STATE_CHANGING:
            origin = request.headers.get("origin")
            if origin not in allowed_origins(port):  # SR-3
                return _err(
                    403,
                    "forbidden_origin",
                    "Cross-origin request refused.",
                    "Use the dashboard page itself.",
                )
            if request.headers.get("x-faultsage-request") != "1":  # SR-4
                return _err(
                    403,
                    "forbidden_origin",
                    "Missing X-FaultSage-Request header.",
                    "Use the dashboard page itself.",
                )
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = csp("ws://127.0.0.1:* ws://localhost:*")
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v
        if request.url.path.startswith(("/api", "/auth")):
            response.headers["Cache-Control"] = "no-store"
        return response

    return guard

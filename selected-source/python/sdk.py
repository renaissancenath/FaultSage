"""FaultSage SDK: capture runtime failures in a deployed app and send them to FaultSage Cloud.

    import faultsage.sdk as fs
    fs.init(api_key=os.environ["FAULTSAGE_API_KEY"], url="https://your-faultsage.example.com",
            environment="production", release="1.4.2")

Everything is redacted on the machine before it is sent. Sending happens on a background thread
with a bounded queue, so a slow or unreachable server never blocks or crashes the app. For web
frameworks, wrap the ASGI or WSGI app with ``ASGIMiddleware`` / ``WSGIMiddleware``.
"""

from __future__ import annotations

import atexit
import os
import platform
import queue
import socket
import sys
import threading
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from faultsage import __version__
from faultsage.collectors.frames import exception_info
from faultsage.redact import redact

_state: dict[str, Any] = {"client": None}


class _Client:
    def __init__(
        self,
        url: str,
        api_key: str,
        environment: str,
        release: str,
        root: Path,
        timeout: float = 5.0,
    ) -> None:
        self.url = url.rstrip("/") + "/api/v1/ingest/events"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": f"faultsage-sdk/{__version__}",
        }
        self.environment = environment
        self.release = release
        self.root = root
        self.timeout = timeout
        self.q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=100)
        self.sent = 0
        self.failed = 0
        self._worker = threading.Thread(target=self._run, name="faultsage-sdk", daemon=True)
        self._worker.start()

    def _run(self) -> None:
        import httpx

        with httpx.Client(timeout=self.timeout, headers=self.headers) as http:
            while True:
                item = self.q.get()
                if item.get("__stop__"):
                    self.q.task_done()
                    return
                try:
                    r = http.post(self.url, json=item)
                    if r.status_code < 300:
                        self.sent += 1
                    else:
                        self.failed += 1
                except Exception:
                    self.failed += 1
                finally:
                    self.q.task_done()

    def capture(
        self, exc: BaseException, tags: dict[str, str] | None = None, level: str = "error"
    ) -> bool:
        event = {
            "exception": exception_info(self.root, exc).model_dump(mode="json"),
            "level": level,
            "environment": self.environment,
            "release": self.release,
            "server_name": socket.gethostname()[:120],
            "timestamp": datetime.now(UTC).isoformat(),
            "tags": {k[:40]: redact(str(v))[:200] for k, v in (tags or {}).items()},
            "context": {"python": platform.python_version(), "platform": platform.system()},
            "sdk": f"faultsage-python/{__version__}",
        }
        try:
            self.q.put_nowait(event)
            return True
        except queue.Full:
            return False

    def flush(self, timeout: float = 5.0) -> None:
        done = threading.Event()

        def wait() -> None:
            self.q.join()
            done.set()

        threading.Thread(target=wait, daemon=True).start()
        done.wait(timeout)


def init(
    api_key: str | None = None,
    url: str | None = None,
    environment: str | None = None,
    release: str | None = None,
    root: str | Path | None = None,
    install_hooks: bool = True,
) -> bool:
    """Start capturing. Returns False (and does nothing) when no key or URL is configured."""
    key = api_key or os.environ.get("FAULTSAGE_API_KEY", "")
    base = url or os.environ.get("FAULTSAGE_URL", "")
    if not key or not base:
        return False
    if not base.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise ValueError("FaultSage URL must use https:// (plain http only for localhost).")
    client = _Client(
        base,
        key,
        environment or os.environ.get("FAULTSAGE_ENVIRONMENT", "production"),
        release or os.environ.get("FAULTSAGE_RELEASE", ""),
        Path(root or Path.cwd()),
    )
    _state["client"] = client
    if install_hooks:
        prev = sys.excepthook

        def hook(t: type[BaseException], e: BaseException, tb: TracebackType | None) -> None:
            if not isinstance(e, KeyboardInterrupt):
                client.capture(e, level="fatal")
                client.flush(2.0)
            prev(t, e, tb)

        sys.excepthook = hook
        prev_thread = threading.excepthook

        def thook(args: threading.ExceptHookArgs) -> None:
            if args.exc_value is not None:
                client.capture(args.exc_value)
            prev_thread(args)

        threading.excepthook = thook
    atexit.register(client.flush, 2.0)
    return True


def capture_exception(exc: BaseException | None = None, **tags: str) -> bool:
    client: _Client | None = _state["client"]
    if client is None:
        return False
    e = exc or sys.exception()
    return client.capture(e, tags) if e is not None else False


def flush(timeout: float = 5.0) -> None:
    client: _Client | None = _state["client"]
    if client is not None:
        client.flush(timeout)


class ASGIMiddleware:
    """Capture unhandled exceptions in any ASGI app (FastAPI, Starlette, Django ASGI)."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        try:
            await self.app(scope, receive, send)
        except Exception as e:
            capture_exception(
                e, path=str(scope.get("path", ""))[:200], method=str(scope.get("method", ""))
            )
            raise


class WSGIMiddleware:
    """Capture unhandled exceptions in any WSGI app (Flask, Django)."""

    def __init__(self, app: Callable[..., Iterable[bytes]]) -> None:
        self.app = app

    def __call__(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        try:
            return self.app(environ, start_response)
        except Exception as e:
            capture_exception(
                e,
                path=str(environ.get("PATH_INFO", ""))[:200],
                method=str(environ.get("REQUEST_METHOD", "")),
            )
            raise

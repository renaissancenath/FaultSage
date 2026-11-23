"""Self-monitoring (F15): FaultSage's own uncaught errors, recorded locally with redaction.

Records go to ~/.faultsage/self/ as JSONL. ``faultsage self-report --export`` writes a file the
user can attach to an issue. Optional forwarding to the user's own FaultSage Cloud or GlitchTip
endpoint only when they configure FAULTSAGE_SELFMON_DSN (off by default, SR-6).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import threading
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any

from faultsage import __version__
from faultsage.analysis.traceback_parser import parse_cpython
from faultsage.redact import redact

RETENTION_DAYS = 30


def self_dir() -> Path:
    base = Path(os.environ.get("FAULTSAGE_HOME", str(Path.home() / ".faultsage")))
    d = base / "self"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fingerprint(exc_type: str, tb_text: str) -> str:
    info = parse_cpython(tb_text, lambda p: "faultsage" in p.replace("\\", "/"))
    frame = info.innermost_project_frame() if info else None
    key = f"{exc_type}|{frame.file_path.rsplit('faultsage', 1)[-1] if frame else ''}|{frame.function if frame else ''}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def record(exc: BaseException, where: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": __version__,
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "where": where,
        "type": type(exc).__qualname__,
        "message": redact(str(exc))[:2000],
        "traceback": redact(tb_text)[:20_000],
        "fingerprint": _fingerprint(type(exc).__qualname__, tb_text),
        "extra": {k: redact(str(v))[:500] for k, v in (extra or {}).items()},
    }
    try:
        with (self_dir() / "errors.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # never let self-monitoring crash the tool
    _forward(entry)
    return entry


def _forward(entry: dict[str, Any]) -> None:
    dsn = os.environ.get("FAULTSAGE_SELFMON_DSN", "")
    if not dsn.startswith("https://"):
        return

    def send() -> None:
        try:
            import httpx

            httpx.post(dsn, json=entry, timeout=5.0)
        except Exception:  # noqa: S110  # nosec B110
            pass

    threading.Thread(target=send, daemon=True).start()


def install(where: str = "cli") -> None:
    previous = sys.excepthook

    def hook(t: type[BaseException], e: BaseException, tb: TracebackType | None) -> None:
        if not isinstance(e, KeyboardInterrupt):
            record(e, where)
        previous(t, e, tb)

    sys.excepthook = hook


def load(limit: int = 50) -> list[dict[str, Any]]:
    path = self_dir() / "errors.jsonl"
    if not path.exists():
        return []
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
            if datetime.fromisoformat(e["at"]) >= cutoff:
                out.append(e)
        except (ValueError, KeyError):
            continue
    return out[-limit:]


def grouped(limit: int = 50) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for e in load(10_000):
        g = groups.setdefault(
            e["fingerprint"],
            {
                "fingerprint": e["fingerprint"],
                "type": e["type"],
                "message": e["message"],
                "count": 0,
                "first": e["at"],
                "last": e["at"],
                "where": e["where"],
                "sample": e,
            },
        )
        g["count"] += 1
        g["last"] = e["at"]
        g["sample"] = e
    return sorted(groups.values(), key=lambda g: g["last"], reverse=True)[:limit]

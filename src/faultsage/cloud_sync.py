"""Optional push of redacted case files to FaultSage Cloud (D-014).

Off by default. Runs only when the user enabled ``[cloud] enabled = true`` and logged in with
``faultsage cloud login``, or ran ``faultsage cloud push``. The API key lives in the user's home
folder (~/.faultsage/cloud.json, user-only permissions), never in the project.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from faultsage import __version__
from faultsage.redact import redact_obj, strip_source
from faultsage.selfmon import hook as selfmon

if TYPE_CHECKING:
    from faultsage.daemon.service import Workspace


def credentials_path() -> Path:
    base = Path(os.environ.get("FAULTSAGE_HOME", str(Path.home() / ".faultsage")))
    base.mkdir(parents=True, exist_ok=True)
    return base / "cloud.json"


def save_credentials(url: str, api_key: str) -> Path:
    p = credentials_path()
    p.write_text(json.dumps({"url": url.rstrip("/"), "api_key": api_key}), encoding="utf-8")
    with contextlib.suppress(OSError):
        p.chmod(0o600)
    return p


def load_credentials() -> dict[str, str] | None:
    p = credentials_path()
    if not p.exists():
        return None
    try:
        data: dict[str, str] = json.loads(p.read_text(encoding="utf-8"))
        return data if data.get("url") and data.get("api_key") else None
    except ValueError:
        return None


def case_payload(ws: Workspace, incident_id: int) -> dict[str, Any]:
    cf = ws.case_file(incident_id)
    data = cf.model_dump(mode="json")
    # Only redacted, already-stored fields leave the machine. No source files, no code excerpts,
    # no patches (D-030).
    return {
        "client": f"faultsage/{__version__}",
        "project": ws.cfg.project.name,
        "case_file": redact_obj(strip_source(data)),
    }


def push_incidents(ws: Workspace, incident_ids: list[int], url: str | None = None) -> int:
    creds = load_credentials()
    if creds is None:
        return 0
    base = (url or ws.cfg.cloud.url or creds["url"]).rstrip("/")
    if not base.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        return 0  # never send over plain HTTP to a remote host
    import httpx

    sent = 0
    for iid in incident_ids:
        try:
            r = httpx.post(
                f"{base}/api/v1/ingest/case-files",
                headers={"Authorization": f"Bearer {creds['api_key']}"},
                json=case_payload(ws, iid),
                timeout=10.0,
            )
            if r.status_code < 300:
                sent += 1
        except Exception as e:
            selfmon.record(e, "cloud_push")
    return sent

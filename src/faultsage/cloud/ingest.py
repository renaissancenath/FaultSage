"""Ingest from the SDK (production runtime errors) and from the CLI (case files)."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from faultsage.analysis.traceback_parser import parse_any
from faultsage.cloud import mailer, plans, triage_agent
from faultsage.cloud.settings import get_settings
from faultsage.cloud.storage import repo
from faultsage.cloud.storage.db import now_iso, tx
from faultsage.errors import PlanLimitError, ValidationFailedError
from faultsage.models.core import CaseFile, ExceptionInfo
from faultsage.redact import redact, redact_obj, strip_source

_EXTERNAL = (
    "site-packages",
    "dist-packages",
    "/lib/python",
    "\\lib\\python",
    "/usr/lib/",
    "<frozen",
    "<",
)


def looks_like_project(path: str) -> bool:
    """The cloud never sees the project root, so a frame is project code unless it is clearly
    installed or standard-library code."""
    p = path.replace("\\", "/")
    return not p.startswith("<") and not any(m.replace("\\", "/") in p for m in _EXTERNAL)


class ErrorEvent(BaseModel):
    """One runtime error sent by ``faultsage.sdk`` (or any client following this schema)."""

    model_config = ConfigDict(extra="ignore")
    exception: ExceptionInfo | None = None
    traceback: str | None = Field(default=None, max_length=100_000)
    message: str | None = Field(default=None, max_length=4000)
    level: Literal["error", "fatal", "warning"] = "error"
    environment: str = Field(default="production", max_length=60)
    release: str = Field(default="", max_length=80)
    server_name: str = Field(default="", max_length=120)
    timestamp: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    context: dict[str, str] = Field(default_factory=dict)
    sdk: str = Field(default="", max_length=60)


class CaseFileUpload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    client: str = ""
    project: str = ""
    case_file: CaseFile


def _check_quota(key: dict[str, Any]) -> None:
    """Refuse when the monthly limit is used up. The drop is counted in its own transaction so
    it is kept even though the request fails."""
    limit = plans.plan(key["plan"]).events_per_month
    with tx() as conn:
        over = repo.usage(conn, key["org_id"])["events"] >= limit
        if over:
            repo.count_event(conn, key["org_id"], dropped=True)
    if over:
        raise PlanLimitError(
            f"Monthly event limit reached ({limit:,} on the {key['plan']} plan). This event was dropped.",
            "Upgrade the plan or wait for the next month. Local FaultSage keeps working.",
        )


def ingest_error(key: dict[str, Any], ev: ErrorEvent) -> dict[str, Any]:
    exc = ev.exception
    if exc is None and ev.traceback:
        exc = parse_any(ev.traceback, looks_like_project)
    if exc is None and not ev.message:
        raise ValidationFailedError(
            "Event has no exception, traceback or message.", "Send at least one."
        )
    payload = redact_obj(ev.model_dump(mode="json", exclude={"traceback"}))
    if exc is not None:
        exc = ExceptionInfo.model_validate(redact_obj(exc.model_dump(mode="json")))
        payload["exception"] = exc.model_dump(mode="json")  # type: ignore[index]
    fingerprint = (
        triage_agent.fingerprint_for(exc) if exc else "message|" + redact(ev.message or "")[:200]
    )
    title = redact(ev.message or "")[:200]
    if exc:
        frame = exc.innermost_project_frame()
        where = (
            f" in {frame.file_path.rsplit('/', 1)[-1]} line {frame.line}"
            if frame and frame.line
            else ""
        )
        first = exc.message.splitlines()[0][:120] if exc.message else ""
        title = f"{exc.type}{(': ' + first) if first else ''}{where}"
    _check_quota(key)
    with tx() as conn:
        iid, created = repo.upsert_issue(
            conn,
            key["project_id"],
            fingerprint,
            title,
            exc.type if exc else None,
            ev.environment,
            ev.release,
            ev.timestamp or now_iso(),
        )
        repo.add_issue_event(conn, iid, key["project_id"], payload)  # type: ignore[arg-type]
        repo.count_event(conn, key["org_id"], dropped=False)
        issue = repo.issue(conn, key["project_id"], iid)
        events = repo.issue_events(conn, iid, 20)
        project = repo.project(conn, key["org_id"], key["project_id"]) or {}
        if issue is None:
            raise ValidationFailedError("Issue disappeared while storing the event.", "Retry.")
        # Triage is cheap (no source code): refresh it on each of the first 20 events, then every
        # 10th, so release and environment facts stay current without work on every event.
        if issue["event_count"] <= 20 or issue["event_count"] % 10 == 0:
            repo.set_triage(conn, iid, triage_agent.triage(issue, events, project))
        owners = [
            m["email"]
            for m in repo.members(conn, key["org_id"])
            if m["role"] in ("owner", "maintainer")
        ]
    if created:
        link = f"{get_settings().base_url}/app/projects/{key['project_id']}/issues/{iid}"
        for email in owners[:10]:
            mailer.new_issue(email, key["project_name"], title, link)
    return {"issue_id": iid, "new": created}


def ingest_case_file(key: dict[str, Any], upload: CaseFileUpload) -> dict[str, Any]:
    cf = upload.case_file
    # Strip source again on the server, so an old or modified client cannot store code (D-030).
    data: dict[str, Any] = cast(
        dict[str, Any], redact_obj(strip_source(cf.model_dump(mode="json")))
    )
    top = cf.hypotheses[0].certainty if cf.hypotheses else None
    _check_quota(key)
    with tx() as conn:
        repo.upsert_case_file(
            conn, key["project_id"], cf.incident_id, redact(cf.title), cf.status, top, data
        )
        repo.count_event(conn, key["org_id"], dropped=False)
    return {"stored": True, "incident_id": cf.incident_id}

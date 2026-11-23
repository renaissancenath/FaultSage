"""Ingest API used by the SDK and the CLI (Bearer API key, no cookies, no CSRF)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from faultsage.cloud import plans
from faultsage.cloud.deps import api_key
from faultsage.cloud.ingest import CaseFileUpload, ErrorEvent, ingest_case_file, ingest_error

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
K = Depends(api_key)


@router.get("/whoami")
def whoami(key: dict[str, Any] = K) -> dict[str, Any]:
    return {
        "project": key["project_name"],
        "project_id": key["project_id"],
        "org": key["org_name"],
        "plan": plans.plan(key["plan"]).name,
    }


@router.post("/events", status_code=202)
def events(ev: ErrorEvent, key: dict[str, Any] = K) -> dict[str, Any]:
    return ingest_error(key, ev)


@router.post("/case-files", status_code=202)
def case_files(upload: CaseFileUpload, key: dict[str, Any] = K) -> dict[str, Any]:
    return ingest_case_file(key, upload)

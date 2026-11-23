"""Spool event models (BACKEND_SCHEMA.md section 3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from faultsage.models.core import ExceptionInfo

SCHEMA_ID = "faultsage.event/1"

EventKind = Literal[
    "test_result",
    "run_result",
    "log_match",
    "file_change",
    "git_change",
    "checkpoint",
    "scan_finding",
]


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TestResultBody(_Body):
    node_id: str = Field(max_length=2000)
    phase: Literal["setup", "call", "teardown"]
    outcome: Literal["passed", "failed", "skipped", "error"]
    duration_s: float = 0.0
    exception: ExceptionInfo | None = None
    longrepr_text: str = Field(default="", max_length=20_000)
    coverage_context: bool = False
    session_id: str = ""


class RunResultBody(_Body):
    argv: list[str]
    exit_code: int
    duration_s: float = 0.0
    stderr_tail: str = ""
    exception: ExceptionInfo | None = None

    @field_validator("stderr_tail")
    @classmethod
    def _cap_lines(cls, v: str) -> str:
        return "\n".join(v.splitlines()[-400:])


class LogMatchBody(_Body):
    file: str
    line_no: int
    pattern: str
    text: str = Field(max_length=8192)


class FileChangeBody(_Body):
    file_path: str
    change: Literal["created", "modified", "deleted", "moved"]
    sha256: str | None = None


class GitChangeBody(_Body):
    head: str
    branch: str | None = None
    changed_files: list[str] = Field(default_factory=list)


class ColumnSpec(_Body):
    name: str
    dtype: str


class CheckpointBody(_Body):
    step: str
    object_type: str
    shape: list[int] | None = None
    columns: list[ColumnSpec] = Field(default_factory=list)


class ScanFindingBody(_Body):
    severity: Literal["error", "warning", "note"]
    rule: str
    file_path: str | None = None
    line: int | None = None
    message: str


BODY_MODELS: dict[str, type[_Body]] = {
    "test_result": TestResultBody,
    "run_result": RunResultBody,
    "log_match": LogMatchBody,
    "file_change": FileChangeBody,
    "git_change": GitChangeBody,
    "checkpoint": CheckpointBody,
    "scan_finding": ScanFindingBody,
}


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Annotated[str, Field(alias="schema")] = SCHEMA_ID
    kind: EventKind
    occurred_at: datetime = Field(default_factory=utcnow)
    project_root: str
    collector: str
    collector_version: str
    body: dict[str, Any]

    @field_validator("schema_")
    @classmethod
    def _schema(cls, v: str) -> str:
        if v != SCHEMA_ID:
            raise ValueError(f"unsupported schema {v!r}")
        return v

    def typed_body(self) -> _Body:
        return BODY_MODELS[self.kind].model_validate(self.body)

    def to_json(self) -> str:
        data = self.model_dump(mode="json", by_alias=True)
        data["occurred_at"] = iso(self.occurred_at)
        import json

        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def validate_event(raw: dict[str, Any]) -> Event:
    """Validate the envelope and the body. Raises pydantic.ValidationError."""
    event = Event.model_validate(raw)
    event.body = event.typed_body().model_dump(mode="json")
    return event

"""Core models shared by spool, engine, API and cloud (BACKEND_SCHEMA.md section 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Certainty = Literal["confirmed", "strong", "possible", "unknown"]
EvidenceSource = Literal[
    "traceback", "git", "checkpoint", "coverage", "log", "import_graph", "history", "scan"
]
IncidentStatus = Literal[
    "open",
    "investigating",
    "fix_proposed",
    "fix_applied",
    "verified",
    "resolved",
    "reopened",
    "dismissed",
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Frame(Model):
    file_path: str
    line: int | None = None
    function: str = "<module>"
    is_project: bool = False
    code: str | None = None


class ExceptionInfo(Model):
    type: str
    message: str = Field(default="", max_length=2000)
    frames: list[Frame] = Field(default_factory=list)
    cause: ExceptionInfo | None = None
    context: ExceptionInfo | None = None

    def innermost_project_frame(self) -> Frame | None:
        for frame in reversed(self.frames):
            if frame.is_project:
                return frame
        return None


class EvidenceItem(Model):
    source: EvidenceSource
    stance: Literal["supports", "contradicts"]
    summary: str
    detail: dict[str, Any] = Field(default_factory=dict)


class Location(Model):
    file_path: str
    line: int | None = None
    function: str | None = None
    class_name: str | None = None
    excerpt: list[tuple[int, str]] | None = None
    available: bool = True


class Hypothesis(Model):
    rank: int
    score: float
    certainty: Certainty
    claim: str
    location: Location | None = None
    pipeline_step: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    weights_version: str = "untrained"
    features: dict[str, float] = Field(default_factory=dict)


class ImpactNode(Model):
    kind: Literal["module", "step", "test"]
    name: str
    relation: Literal["direct", "indirect"]
    basis: Literal["known", "inferred"]
    depth: int


SuggestionState = Literal["proposed", "stale", "applied", "rejected", "failed"]


class Suggestion(Model):
    id: int = 0
    origin: Literal["rule", "local_model"] = "rule"
    rule_id: str | None = None
    explanation: str
    patch_diff: str | None = None
    base_hashes: dict[str, str] = Field(default_factory=dict)
    files: list[str] = Field(default_factory=list)
    verify_node_ids: list[str] = Field(default_factory=list)
    verify_command: str = ""
    state: SuggestionState = "proposed"


class TestOutcome(Model):
    node_id: str
    outcome: Literal["passed", "failed", "skipped", "error"]
    duration_s: float = 0.0


VerificationResult = Literal["resolved", "still_failing", "new_failures", "timeout", "error"]


class Verification(Model):
    id: int
    incident_id: int
    result: VerificationResult | None = None
    tests: list[TestOutcome] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None


class TimelineEntry(Model):
    at: datetime
    kind: Literal["occurrence", "analysis", "suggestion", "approval", "verification", "status"]
    text: str


class Approval(Model):
    id: int
    suggestion_id: int
    outcome: Literal["pending", "applied", "refused", "failed_restored"]
    outcome_detail: str | None = None
    backup_path: str | None = None


class CaseFile(Model):
    incident_id: int
    title: str
    status: str
    exception: ExceptionInfo | None = None
    failing_tests: list[str] = Field(default_factory=list)
    raise_site: Location | None = None
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    impacts: list[ImpactNode] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    verifications: list[Verification] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int = 1
    analysis_error: str | None = None
    missing_evidence: list[str] = Field(default_factory=list)


class IncidentSummary(Model):
    id: int
    title: str
    status: str
    exception_type: str | None = None
    top_certainty: Certainty | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int


class GraphNode(Model):
    id: str
    label: str
    kind: Literal["module", "step", "test"]
    state: Literal["passed", "failed", "warning", "not_run"] = "not_run"
    on_failure_path: bool = False


class GraphEdge(Model):
    source: str
    target: str
    basis: Literal["known", "inferred"] = "known"
    on_failure_path: bool = False


class Graph(Model):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class Page(Model):
    items: list[Any]
    next_cursor: str | None = None

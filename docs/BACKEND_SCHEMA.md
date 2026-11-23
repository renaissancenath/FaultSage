# FaultSage: Backend Schema

Contracts between collectors, daemon, analysis engine, API and dashboard. Pydantic models in `src/faultsage/models/` are the code source of truth; this document must match them. The dashboard's TypeScript types are generated from the FastAPI OpenAPI schema.

---

## 1. Conventions

- JSON, UTF-8, `snake_case` keys.
- Times: ISO 8601 UTC with `Z` (`2026-12-01T09:14:03.120Z`). The UI converts to local time.
- IDs: integers in DB; shown to users with prefixes `I-` (incident), `S-` (suggestion), `A-` (approval), `V-` (verification).
- Paths: POSIX style, relative to project root.
- All text that came from the user's project (messages, excerpts, log lines) is redacted before storage and is plain text.
- Errors use one shape (section 5).

## 2. Core models

```python
class Frame(BaseModel):
    file_path: str  # relative if inside project, else "<external>/pkg/mod.py"
    line: int | None
    function: str
    is_project: bool
    code: str | None  # the source line, redacted


class ExceptionInfo(BaseModel):
    type: str  # "KeyError"
    message: str  # redacted, max 2,000 chars
    frames: list[Frame]  # outermost first
    cause: "ExceptionInfo | None" = None
    context: "ExceptionInfo | None" = None


Certainty = Literal["confirmed", "strong", "possible", "unknown"]


class EvidenceItem(BaseModel):
    source: Literal[
        "traceback", "git", "checkpoint", "coverage", "log", "import_graph", "history", "scan"
    ]
    stance: Literal["supports", "contradicts"]
    summary: str  # "clean.py:31 changed 2 h ago, renamed column"
    detail: dict  # source-specific, see 2.1


class Location(BaseModel):
    file_path: str
    line: int | None
    function: str | None
    class_name: str | None
    excerpt: list[tuple[int, str]] | None  # (line number, text)
    available: bool  # False -> UI shows "line not available"


class Hypothesis(BaseModel):
    rank: int
    score: float
    certainty: Certainty
    claim: str
    location: Location | None
    pipeline_step: str | None
    evidence: list[EvidenceItem]
    weights_version: str  # run id or "untrained"


class ImpactNode(BaseModel):
    kind: Literal["module", "step", "test"]
    name: str
    relation: Literal["direct", "indirect"]
    basis: Literal["known", "inferred"]
    depth: int


class Suggestion(BaseModel):
    id: int
    origin: Literal["rule", "local_model"]
    rule_id: str | None
    explanation: str
    patch_diff: str | None  # None = no safe patch
    files: list[str]
    verify_node_ids: list[str]
    verify_command: str  # display only, e.g. "python -m pytest tests/test_train.py::test_fit"
    state: Literal["proposed", "stale", "applied", "rejected", "failed"]


class CaseFile(BaseModel):
    incident_id: int
    title: str
    status: str
    exception: ExceptionInfo | None
    failing_tests: list[str]
    raise_site: Location | None
    hypotheses: list[Hypothesis]
    impacts: list[ImpactNode]
    suggestions: list[Suggestion]
    verifications: list["Verification"]
    timeline: list["TimelineEntry"]
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
```

### 2.1 Evidence detail shapes

| source | detail keys |
|---|---|
| traceback | `frame_index`, `depth_from_raise`, `is_project` |
| git | `commit`, `author_time`, `file_path`, `hunk_start`, `hunk_end`, `overlaps_candidate` |
| checkpoint | `step`, `expected_columns`, `found_columns`, `closest_matches` |
| coverage | `ochiai`, `ef`, `ep`, `nf`, `np` |
| log | `file`, `line_no`, `pattern`, `text` |
| import_graph | `path` (list of modules), `hops` |
| history | `incident_ids`, `same_location` |
| scan | `rule`, `message` |

## 3. Spool events (collector to daemon)

Each line in `.faultsage/spool/<collector>-<pid>-<n>.jsonl`:

```json
{
  "schema": "faultsage.event/1",
  "kind": "test_result",
  "occurred_at": "2026-12-01T09:14:03.120Z",
  "project_root": "C:/code/churn-pipeline",
  "collector": "pytest_plugin",
  "collector_version": "0.1.0",
  "body": {}
}
```

| kind | body |
|---|---|
| `test_result` | `node_id`, `phase` (setup, call, teardown), `outcome` (passed, failed, skipped, error), `duration_s`, `exception` (ExceptionInfo or null), `longrepr_text` (redacted, max 20 KB), `coverage_context` (bool), `session_id` |
| `run_result` | `argv` (list), `exit_code`, `duration_s`, `stderr_tail` (redacted, max 400 lines), `exception` |
| `log_match` | `file`, `line_no`, `pattern`, `text` (redacted, max 8 KB) |
| `file_change` | `file_path`, `change` (created, modified, deleted, moved), `sha256` |
| `git_change` | `head`, `branch`, `changed_files` |
| `checkpoint` | `step`, `object_type`, `shape`, `columns` ([{name, dtype}]) |
| `scan_finding` | `severity`, `rule`, `file_path`, `line`, `message` |

Invalid lines are moved to `spool/rejected/` with the validation error.

## 4. HTTP API (127.0.0.1 only)

All routes under `/api`, JSON, cookie auth. State-changing routes need `Origin` matching the dashboard origin and header `X-FaultSage-Request: 1`.

| Method | Path | Purpose | Response |
|---|---|---|---|
| POST | `/auth/session` | Exchange one-time token for cookie | 204 |
| GET | `/api/status` | Daemon state, project, signals, open count | `Status` |
| POST | `/api/watch/pause` | Pause ingest | `Status` |
| POST | `/api/watch/resume` | Resume | `Status` |
| GET | `/api/incidents?status=&q=&limit=&cursor=` | List | `Page[IncidentSummary]` |
| GET | `/api/incidents/{id}` | Case file | `CaseFile` |
| POST | `/api/incidents/{id}/dismiss` | Dismiss | `IncidentSummary` |
| POST | `/api/incidents/{id}/resolve` | Mark resolved after verified | `IncidentSummary` |
| GET | `/api/incidents/{id}/export?format=md|json` | Export | file |
| GET | `/api/graph?kind=imports|pipeline&focus={incident_id}` | Graph for display | `Graph` |
| POST | `/api/suggestions/{id}/approve` | Create approval and apply | `Approval` |
| POST | `/api/incidents/{id}/verify` | Start verification | `Verification` (202) |
| GET | `/api/verifications/{id}` | Verification status | `Verification` |
| POST | `/api/scan` | Start deep scan | `ScanRun` (202) |
| GET | `/api/scan/{id}` | Scan results | `ScanRun` |
| GET | `/api/pipeline` | Steps with last status and checkpoint | `Pipeline` |
| GET | `/api/bench/runs` | Run records found in `results/runs` | `list[BenchRunSummary]` |
| GET | `/api/bench/runs/{run_id}` | Metrics and cases | `BenchRun` |
| GET | `/api/settings` | Current config (no secrets exist) | `Settings` |
| PUT | `/api/settings` | Update signals, retention, port (restart notice) | `Settings` |
| POST | `/api/purge` | Purge with `{"confirm": "purge <project name>"}` | 204 |

```python
class Approval(BaseModel):
    id: int
    suggestion_id: int
    outcome: Literal["pending", "applied", "refused", "failed_restored"]
    outcome_detail: str | None
    backup_path: str | None


class Verification(BaseModel):
    id: int
    incident_id: int
    result: Literal["resolved", "still_failing", "new_failures", "timeout", "error"] | None
    tests: list[TestOutcome]
    started_at: datetime
    finished_at: datetime | None


class Graph(BaseModel):
    nodes: list[GraphNode]  # id, label, kind, state, on_failure_path
    edges: list[GraphEdge]  # source, target, basis (known|inferred), on_failure_path
```

## 5. Error shape

```json
{
  "error": {
    "code": "patch_stale",
    "message": "src/churn/clean.py changed since this suggestion was made.",
    "next_step": "Regenerate the suggestion from the case file."
  }
}
```

Codes: `not_found`, `validation_failed`, `unauthorised`, `forbidden_origin`, `patch_stale`, `git_dirty`, `path_outside_project`, `verify_running`, `daemon_paused`, `db_busy`, `internal_error`. `internal_error` never includes a stack trace; the trace goes to self-monitoring.

## 6. WebSocket

`GET /ws/events` (cookie auth, Origin checked). Server to client only:

| type | payload |
|---|---|
| `status.changed` | `Status` |
| `incident.created` | `IncidentSummary` |
| `incident.updated` | `{id, status, updated_at}` |
| `verification.updated` | `{id, incident_id, result}` |
| `scan.finished` | `{id, findings_count}` |

Client refetches details by id. No data-heavy pushes.

## 7. Benchmark records

`results/runs/<run_id>/run.json` follows DATASETS.md section 6. `cases.jsonl` lines:

```json
{"case_id":"pandas-12","reproduced":true,"truth":{"files":["pandas/core/frame.py"],"functions":["DataFrame.apply"],"failing_tests":["..."]},
 "predictions":{"faultsage":[...],"top_frame":[...],"ochiai":[...],"recent":[...],"random":[...]},
 "blast_radius":{"predicted_tests":[...],"actual_failing_tests":[...]},
 "verify":{"buggy":"still_failing","fixed":"resolved"}}
```

## 8. FaultSage Cloud API (`/api/v1`)

Browser routes use the session cookie; every POST, PUT and DELETE also needs header `X-CSRF-Token` equal to the `fs_csrf` cookie. Ingest routes use `Authorization: Bearer fsk_...` instead. Errors use the shape in section 5, plus codes `plan_limit` (402), `rate_limited` (429), `forbidden` (403).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/meta` | Mode, version, plans, which optional features are on |
| POST | `/api/v1/auth/signup` | `{email, password, name?, workspace?}`; starts a session |
| POST | `/api/v1/auth/login` / `logout` / `logout-everywhere` | Sessions |
| POST | `/api/v1/auth/verify-email` / `resend-verification` | Email confirmation (token from the email link fragment) |
| POST | `/api/v1/auth/forgot-password` / `reset-password` / `change-password` | Passwords |
| GET | `/api/v1/auth/github/start`, `/github/callback` | Optional GitHub OAuth |
| GET, PUT | `/api/v1/me`; POST `/api/v1/me/delete` | Account, usage, plan; deletion needs typed confirmation and password |
| PUT | `/api/v1/org`; GET `/api/v1/org/members`, `/org/audit` | Workspace |
| POST, PUT, DELETE | `/api/v1/org/members/invite`, `/org/members/{uid}` | Members and roles (owner only) |
| GET, POST | `/api/v1/projects`; GET, PUT `/projects/{id}`; POST `/projects/{id}/delete` | Projects |
| GET, POST, DELETE | `/api/v1/projects/{id}/keys[/{kid}]` | API keys (raw key returned once) |
| GET | `/api/v1/projects/{id}/issues[/{iid}]` | Production errors with triage and recent events |
| PUT, POST | `/issues/{iid}/status`, `/issues/{iid}/triage` | Status, rerun triage |
| GET | `/api/v1/projects/{id}/case-files[/{cid}]` | Case files synced from the CLI |
| POST | `/api/v1/billing/upgrade`, `/billing/webhook/lemonsqueezy` | Plan change request; signed provider webhook |
| GET | `/api/v1/ingest/whoami` | Key check used by `faultsage cloud login` |
| POST | `/api/v1/ingest/events` | SDK error event (below), 202 |
| POST | `/api/v1/ingest/case-files` | `{client, project, case_file: CaseFile}`, 202 |
| GET | `/healthz` | Liveness and database check |

Error event body (`faultsage.cloud.ingest.ErrorEvent`): `exception` (ExceptionInfo) or `traceback` (text) or `message`; `level`, `environment`, `release`, `server_name`, `timestamp`, `tags`, `context`, `sdk`. Grouped by the same signature as local incidents (FR-12).

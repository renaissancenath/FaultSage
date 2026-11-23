# FaultSage: Technical Requirements Document

| Field | Value |
|---|---|
| Version | 2.0 |
| Reads with | PRD.md (what), ARCHITECTURE.md (structure), BACKEND_SCHEMA.md (contracts), DATABASE.md (storage) |

This document turns the PRD into testable technical requirements. Every requirement has an ID so code, tests and pull requests can reference it.

---

## 1. Environment

| Item | Requirement |
|---|---|
| Python (FaultSage itself) | 3.11 or 3.12 |
| Python (monitored project) | 3.8+ for the pytest plugin and `faultsage run`; older projects only in benchmark containers |
| OS | Windows 10/11 (PowerShell 7) and Ubuntu 22.04/24.04 (native or WSL2) |
| Node.js | 20 LTS or 22 LTS (dashboard build only; end users get prebuilt static files) |
| Benchmarks | WSL2 Ubuntu + Docker Engine (open source, Apache-2.0) or Podman. Docker Desktop is not required. |
| Network | Not required at runtime. Only `faultsage bench fetch` and package installs use the network. |

---

## 2. Free and open-source only

Every dependency must be free and open source under an OSI licence, with no paid tier, account, API key or usage quota required for any feature.

| Area | Choice | Licence |
|---|---|---|
| CLI | Typer (on Click) | MIT / BSD-3 |
| File watching | watchdog | Apache-2.0 |
| Web API | FastAPI, Starlette, Uvicorn | MIT / BSD-3 / BSD-3 |
| Validation | Pydantic v2 | MIT |
| Storage | SQLite via Python `sqlite3` | Public domain / PSF |
| Graphs | NetworkX | BSD-3 |
| Coverage | coverage.py, pytest-cov | Apache-2.0 / MIT |
| Tests | pytest, hypothesis | MIT / MPL-2.0 |
| Static checks | Ruff, mypy | MIT / MIT |
| Security checks | Bandit, pip-audit, gitleaks, Semgrep Community Edition | Apache-2.0 / Apache-2.0 / MIT / LGPL-2.1 |
| Frontend | React, Vite, TypeScript | MIT / MIT / Apache-2.0 |
| Graph UI | React Flow (`@xyflow/react`, core package only) | MIT |
| Icons | Phosphor Icons (regular weight) | MIT |
| Fonts | IBM Plex Sans, IBM Plex Mono (self-hosted) | SIL OFL 1.1 |
| Frontend tests | Vitest, Playwright, axe-core | MIT / Apache-2.0 / MPL-2.0 |
| Frontend lint/format | Biome | MIT / Apache-2.0 |
| Optional local model | Ollama + an open-weight code model whose card shows Apache-2.0 or MIT | MIT + model licence |
| Optional error inbox | GlitchTip (self-hosted) | MIT |
| Cloud database access | SQLAlchemy Core, psycopg 3 (D-016) | MIT / LGPL-3.0 |
| Cloud passwords | argon2-cffi (D-015) | MIT |
| HTTP client (cloud sync, SDK, OAuth) | httpx | BSD-3 |
| Routing (web) | React Router 7 | MIT |
| Hosting (optional) | Render free web service, Neon free Postgres, or any VPS with Docker Compose and Caddy (D-018, D-019) | Caddy: Apache-2.0 |
| CI | GitHub Actions on a **public** repository (no minute quota for public repos), plus `tools/ci_local` scripts that run the same checks offline | n/a |

Rule: adding a dependency requires an entry in this table and in DECISIONS.md. Anything with a paid plan needed for the feature we use is rejected.

---

## 3. Functional requirements

### 3.1 Project connection
- **FR-1** `faultsage init [PATH]` resolves the project root (nearest folder with `pyproject.toml`, `setup.py`, `requirements*.txt` or `.git`).
- **FR-2** Detects: Python source folders, test folders (`tests/`, `test/`, `*_test.py`, `test_*.py`), dependency files, git repo, `.faultsage/pipeline.toml`.
- **FR-3** Writes `.faultsage/config.toml` with every signal listed and enabled flags. Never overwrites an existing config without `--force` and a backup.
- **FR-4** Adds `.faultsage/` data folders to `.gitignore` only after asking (prompt or `--yes`).

### 3.2 Signal collection
- **FR-5** Pytest plugin (`pytest11` entry point `faultsage`) emits one event per test report (`setup`, `call`, `teardown`) with outcome, duration, node id, and for failures the full traceback as structured frames.
- **FR-6** The plugin writes events to the spool (`.faultsage/spool/*.jsonl`) and never blocks or fails the test run. Any plugin error is swallowed and written to `.faultsage/logs/plugin.log`.
- **FR-7** `faultsage run -- <cmd> [args]` executes the command without a shell, streams output unchanged to the terminal, records exit code, stderr tail (last 400 lines, redacted) and uncaught Python exceptions with structured frames (when the command is `python script.py` or `python -m module`, FaultSage runs it through a small `runpy` launcher that installs an exception hook; other commands are captured by exit code and stderr only).
- **FR-8** Log tailer reads only files listed in config, follows rotation, applies configured regex patterns, caps line length at 8 KB.
- **FR-9** File watcher reports saves under the project root except ignored paths (`.git`, `.venv`, `node_modules`, `.faultsage`, `__pycache__`).
- **FR-10** Git reader uses the `git` CLI (subprocess, no shell) to get HEAD, changed files and hunks since the last green run.
- **FR-11** Pipeline checkpoints: `faultsage.checkpoint(obj, step="clean")` records type, shape and column names (never values) of pandas/polars DataFrames, dicts and arrays.

### 3.3 Incidents
- **FR-12** Signature = exception type + normalised path of the innermost project frame + function name. Same signature within an open incident appends an occurrence instead of creating a new incident.
- **FR-13** Incident states: `open`, `investigating`, `fix_proposed`, `fix_applied`, `verified`, `resolved`, `reopened`, `dismissed`.

### 3.4 Analysis
- **FR-14** Traceback parser handles CPython tracebacks including chained exceptions (`During handling...`, `The above exception was the direct cause...`) and pytest's long and short formats.
- **FR-15** Project frames are those under the project root and not under virtualenv or site-packages.
- **FR-16** AST index maps every line to its enclosing function and class.
- **FR-17** Import graph built from AST `import` / `from` statements, resolving relative imports.
- **FR-18** Spectrum-based localisation: when the run used `--cov-context=test`, compute Ochiai per line and per function: `ef / sqrt((ef + nf) * (ef + ep))`.
- **FR-19** Ranker computes a score per candidate as a weighted sum of normalised features (traceback depth, Ochiai, recently changed, schema mismatch, import distance, recurrence). Weights are learned with logistic regression on the development split only and ship in the private `faultsage_engine` package with the run id that produced them (D-032). Without that package, the built-in engine ranks traceback frames only.
- **FR-20** Certainty labels:
  - **Confirmed**: directly observed fact (the exception, the line that raised, a column that is missing in a checkpoint).
  - **Strong**: top candidate with score margin above the calibrated threshold and at least two independent evidence sources.
  - **Possible**: in the candidate list with at least one evidence source.
  - **Unknown**: not enough evidence. The UI must say so.
- **FR-21** Blast radius: reverse BFS on the combined import and pipeline graph from the top candidate's module or step, max depth configurable (default 4), each node tagged `known` or `inferred` and `direct` or `indirect`.

### 3.5 Fixes, approval, verification
- **FR-22** Fix rules are plugins implementing `match(incident) -> bool` and `suggest(incident) -> Suggestion`. Required MVP rules: missing dict key or DataFrame column (with closest-name matches from checkpoint evidence via `difflib`), `ModuleNotFoundError`/`ImportError`, `FileNotFoundError`, missing environment variable, `AttributeError` on `None`, wrong call arity from AST signature, dependency version conflict from installed metadata.
- **FR-23** Patches are unified diffs computed against the current file hash. A patch whose base hash no longer matches is marked stale and cannot be applied.
- **FR-24** Apply requires: an approval record, path inside project root (resolved, no symlink escape), git tree clean or user-confirmed stash, backup written to `.faultsage/backups/<approval_id>/`.
- **FR-25** Verify runs, without a shell, `python -m pytest <node ids>` for failing tests plus affected tests, with a timeout (default 600 s), and records per-test results.
- **FR-26** Verification commands come only from: pytest node ids, or commands the user declared in config. FaultSage never runs a command invented by a rule or a model.

### 3.6 Dashboard and API
- **FR-27** Uvicorn binds to `127.0.0.1` only. Port 8765 by default, configurable.
- **FR-28** Session token: 32 random bytes from `secrets`, printed once, exchanged at `/auth/session` for an HttpOnly, SameSite=Strict cookie. See 02_LOGIN-RULES.md.
- **FR-29** Live updates through one WebSocket channel `/ws/events`.
- **FR-30** The dashboard is prebuilt static files served by FastAPI. No CDN, no external fonts, no analytics.

### 3.7 Benchmarks
- **FR-31** `faultsage bench fetch <dataset>` downloads from the official source and records the commit or DOI version.
- **FR-32** `faultsage bench run <dataset> --split test` runs each case in an isolated container with networking disabled after dependency install.
- **FR-33** Every run writes `results/runs/<run_id>/run.json` (inputs, versions, case ids, seeds, metrics) and `cases.jsonl` (per-case predictions and ground truth).
- **FR-34** Baselines are run in the same run: random, top project stack frame, Ochiai only, recently changed only, all importers (blast radius).

### 3.8 Retention and export
- **FR-35** Events older than the configured retention (default 30 days) are deleted on daemon start. Incidents are kept until purged.
- **FR-36** `faultsage export <incident> --format md|json`; `faultsage purge [--all]` deletes local data after confirmation.

---

## 4. Non-functional requirements

| ID | Requirement | Measured by |
|---|---|---|
| NFR-1 | Detection delay under 2 s median from pytest session end to incident in UI | Integration timing test |
| NFR-2 | Daemon idle under 2% CPU and 200 MB RSS | Soak test with `psutil` sampling |
| NFR-3 | Pytest plugin adds under 5% to test wall time without coverage | Benchmark on a real BugsInPy project |
| NFR-4 | Analysis of one incident under 3 s for projects up to 2,000 Python files | Timing test on pandas checkout |
| NFR-5 | Dashboard first render under 1.5 s on localhost | Playwright trace |
| NFR-6 | 8-hour watch session without crash or memory growth over 20% | Soak test record |
| NFR-7 | No outbound network during runtime commands | Test with network namespace disabled |
| NFR-8 | WCAG 2.2 AA | axe-core in Playwright, manual keyboard pass |
| NFR-9 | Every API response under 200 ms p95 for local reads | API test |
| NFR-10 | Works offline after install | Manual check, recorded |

---

## 5. Interfaces

### 5.1 CLI

| Command | Purpose | Writes to project? |
|---|---|---|
| `faultsage init [PATH] [--force] [--yes]` | Detect project, write config | Only `.faultsage/` and, if approved, `.gitignore` |
| `faultsage watch [--port N]` | Start daemon and dashboard | No |
| `faultsage pause` / `resume` / `stop` | Control daemon | No |
| `faultsage status` | Show daemon state and open incidents | No |
| `faultsage scan` | Deep scan | No |
| `faultsage run -- CMD...` | Run a command and capture failures | No |
| `faultsage incidents [--open]` | List incidents | No |
| `faultsage show ID` | Print a case file | No |
| `faultsage apply SUGGESTION_ID` | Apply patch after typed confirmation | Yes, gated |
| `faultsage verify INCIDENT_ID` | Rerun failing and affected tests | No (tests may write their own temp files) |
| `faultsage dashboard` | Open browser with session token | No |
| `faultsage export ID --format md|json` | Export | Writes export file where user says |
| `faultsage purge [--all]` | Delete local data | Deletes `.faultsage/` data after confirmation |
| `faultsage bench fetch|run|report` | Benchmarks | Only `data/` and `results/` of the FaultSage repo |

### 5.2 Event spool format
One JSON object per line, schema in BACKEND_SCHEMA.md section 3. Files rotate at 10 MB.

### 5.3 HTTP and WebSocket
Defined in BACKEND_SCHEMA.md.

### 5.4 Configuration
`.faultsage/config.toml`:

```toml
[project]
name = "churn-pipeline"
root = "."

[signals]
pytest = true
run_wrapper = true
git = true
file_watch = true
logs = ["logs/app.log"]
log_patterns = ["ERROR", "Traceback \\(most recent call last\\)"]

[analysis]
coverage_contexts = false
blast_radius_depth = 4

[verify]
timeout_seconds = 600
extra_commands = []        # only commands you write here can ever be run

[dashboard]
port = 8765

[model]
enabled = false            # optional local Ollama model
endpoint = "http://127.0.0.1:11434"
name = ""

[retention]
event_days = 30
```

`.faultsage/pipeline.toml`:

```toml
[[step]]
name = "load"
command = ["python", "-m", "pipeline.load"]
outputs = ["raw_transactions"]

[[step]]
name = "clean"
command = ["python", "-m", "pipeline.clean"]
inputs = ["raw_transactions"]
outputs = ["clean_transactions"]
```

---

## 6. Algorithms (summary)

1. **Candidate generation**: all project frames in the traceback, all lines with Ochiai above 0 (if coverage), all functions changed since last green run that are reachable from the failing test in the import graph, all pipeline steps upstream of the failing step.
2. **Features** (each normalised to 0..1): `tb_depth` (innermost project frame = 1), `ochiai`, `changed_recently` (0/1, plus hunk overlap), `schema_mismatch` (0/1 with column evidence), `import_distance` (1 / (1 + hops)), `recurrence` (prior incidents with same location).
3. **Score**: logistic regression trained on BugsInPy development projects. Every run record names the weights version and the SHA-256 of the weights file it used, so results stay traceable while the coefficients stay in the private engine (D-032).
4. **Calibration**: the Strong threshold is chosen on the development split so that Strong top-1 precision is reported, not assumed.
5. **Blast radius**: reverse reachability, then intersect with per-test coverage when available to list affected tests.

---

## 7. Constraints

- No secrets, values or row data from user projects are stored. Checkpoints store column names, dtypes and shapes only.
- No `shell=True`, no `eval`, no `exec` on user-provided strings, no pickle loading of untrusted data.
- FaultSage never pushes to git, never deletes user files, never runs `pip install` in the user's environment.
- Benchmark code is untrusted and runs only in containers.

# FaultSage: Product Requirements Document

| Field | Value |
|---|---|
| Version | 2.0 |
| Date | November 2026 |
| Owner | Renaissance Nath |
| Status | Stages 1 to 7 built and tested. Hosted service added by D-014. No benchmark run recorded yet. |
| Related | TRD.md, ARCHITECTURE.md, DATASETS.md, TESTING.md |

---

## 1. Product overview

FaultSage is a local tool you install into a Python project. It watches the project while you work, and when something breaks it answers eight questions:

1. What failed?
2. Where did it fail (file, line, function)?
3. Why did it probably fail, and how sure are we?
4. What evidence supports that answer, and what contradicts it?
5. Which other files, pipeline steps and tests are affected?
6. What should you change?
7. How do you check that the change worked?
8. Did the check pass?

It has two parts:

- **A command-line tool** (`faultsage init`, `watch`, `scan`, `run`, `verify`, `dashboard`, `bench`) that collects signals from pytest, Python exceptions, logs, git and declared pipeline steps.
- **A local web dashboard** at `http://127.0.0.1:8765` that shows incidents as case files: the failure, the ranked causes with evidence, the affected components on a graph, a suggested patch, and the verification result.

Everything runs on the user's machine. No code, log or result leaves the machine unless the user exports it.

FaultSage is also measured. Its root-cause ranking, file localisation and blast-radius estimates are evaluated on public benchmarks of real bugs from real projects (BugsInPy, JunoBench, LogSage, LogChunks) against simple baselines. No synthetic or demo data is used for any reported number.

**One-line description:** FaultSage watches your Python project, finds the line that broke it, shows what else it broke, and checks your fix.

---

## 2. Problem

A Python error message tells you where the program stopped. It rarely tells you why.

Example: a training step fails with `KeyError: 'transaction_amount'`. The real cause is three steps upstream, where a preprocessing function started producing a column called `amount` after a refactor. To find this, a developer has to read the traceback, open several files, compare column names between steps, check the last git changes and rerun tests. Then they have to work out what else was affected (features, model, report) and confirm the fix did not break something new.

The specific pains:

| Pain | What happens today |
|---|---|
| The traceback points at the symptom | The developer edits the line that crashed, not the line that caused it |
| Signals are scattered | Test output, logs, git diff and data schemas live in different places |
| Impact is invisible | Nobody knows which downstream steps or tests are now unsafe |
| Fixes are not verified | A change "looks right" and is merged without rerunning the failing test |
| Learners are lost | Students see a 40-line traceback and do not know which frame matters |
| Tool claims are unmeasured | Most debugging assistants publish no accuracy on public data |

---

## 3. Goal

Build an installable, local, free tool that:

1. Connects to an existing Python project in under one minute.
2. Detects failures from tests, exceptions, logs and pipeline steps while the user works.
3. Ranks likely root causes using evidence, and labels each claim as **Confirmed**, **Strong**, **Possible** or **Unknown**.
4. Points to the file, line and function when the evidence supports it, and says so when it does not.
5. Shows the blast radius: which modules, tests and pipeline steps depend on the failing code.
6. Suggests a fix as a patch preview and never changes files without the user's approval.
7. Reruns the relevant tests and reports whether the failure is resolved.
8. Keeps an incident history.
9. Publishes reproducible accuracy numbers on real benchmarks, compared against baselines, including the cases where it fails.

**Non-goals for v1:** other languages, automatic code changes, production APM, distributed tracing across services, model drift monitoring. Cloud hosting and team accounts were added later as an optional part (D-014); the local tool needs neither.

---

## 4. Target users and what they need

| User | Situation | What they need from FaultSage |
|---|---|---|
| Students and learners | Running coursework and portfolio projects, often stuck on tracebacks | Which frame matters, a plain explanation, and one concrete next step |
| Python developers | Working on libraries, APIs, scripts | Fast file and line localisation, recent-change evidence, a verified fix |
| Data engineers | Running multi-step pipelines (ingest, clean, transform, load) | Which step broke, which upstream change caused it, which downstream steps are now unsafe |
| ML engineers | Preprocessing, features, training, evaluation | Schema mismatches between steps, affected models and reports |
| DevOps and platform engineers | Build and CI failures | The log lines that explain the failure, not the whole log |
| Team leads | Tracking project health | Open incidents, resolution status, history |
| Non-technical readers | Reading an incident someone shared | What broke, why it matters, what is being done, in plain language |

---

## 5. Core features

Each feature lists what it does and the evidence rule it must follow.

### F1. Project connector (CLI)
`faultsage init` detects the project root, Python files, `pyproject.toml` or `requirements*.txt`, test folders, git repository and any declared pipeline. It writes `.faultsage/config.toml` listing exactly which signals are enabled. The user edits this file to grant or remove permissions.

### F2. Watch mode
`faultsage watch` runs a local daemon that:
- receives events from the FaultSage pytest plugin (each test result with traceback),
- receives events from `faultsage run -- <command>` (exit code, stderr, uncaught exceptions),
- tails log files listed in the config,
- watches file saves and git HEAD changes,
- records checkpoints from declared pipeline steps.

Watch mode shows a visible status (running, paused, stopped). `faultsage pause` and `faultsage stop` work at any time.

### F3. Deep scan
`faultsage scan` is a one-off check: broken imports, missing dependencies, circular imports, undefined names (via Ruff), pipeline steps whose declared inputs no step produces, and tests that currently fail. Scan does not run in the background.

### F4. Incident creation
A failed test, uncaught exception, failed pipeline step or matching log pattern creates an incident. Repeated failures with the same signature (exception type + normalised top project frame) are grouped into one incident.

### F5. Root-cause ranking ("prove-it ranking")
For each incident, FaultSage builds candidate locations (functions and lines) and scores them from evidence:
- position in the traceback (project frames only),
- spectrum-based score (Ochiai) from per-test coverage, when coverage was collected,
- changed in git since the last passing run,
- schema evidence from pipeline checkpoints (expected vs actual columns),
- distance in the import graph from the failing test,
- earlier incidents with the same signature.

Each candidate shows the evidence for and against it and a certainty label. The output is a ranked list of hypotheses, never a claim of proof.

### F6. File-level diagnosis
Shows file path, line, function or class, the error message and a code excerpt with the suspected line marked. If the source line is not available (compiled code, missing file), FaultSage says "line not available" and does not guess.

### F7. Pipeline and dependency map
A graph of modules (from Python imports) and pipeline steps (from `.faultsage/pipeline.toml`). Nodes show state with shape and text: passed, failed, warning, not run. Clicking a node shows its incidents. Known edges (imports, declared step inputs) are drawn solid. Inferred edges (for example, name similarity) are dashed and labelled "inferred".

### F8. Blast radius
From the suspected root location, FaultSage walks the reverse dependency graph and lists:
- directly affected (imports the failing module, or consumes the failing step's output),
- indirectly affected (further downstream),
- tests that cover the affected code.

Each item is labelled "known" or "inferred".

### F9. Fix recommendation
A rule library for common Python failures (missing key or column, import errors, missing files or environment variables, wrong signatures, None attribute access, version conflicts). Each recommendation contains: plain-language explanation, likely cause, evidence, a patch preview (unified diff) where a safe patch exists, and the exact command to verify it.

An optional local language model (through Ollama, off by default) may draft explanations and patches. Its output is labelled "model suggestion" and goes through the same preview and approval gate.

### F10. Approval gate for changes
FaultSage never writes to project files on its own. Applying a patch requires a click on "Apply patch" in the dashboard or `faultsage apply <id>` in the terminal, a clean or stashed git state, and creates a backup. Every apply is recorded in the approvals log.

### F11. Verification
After a fix (FaultSage's or the user's own), `faultsage verify <incident>` reruns the failing tests and the tests in the blast radius. The incident shows: failure resolved or still present, new failures, and which downstream tests now pass.

### F12. Incident history and reports
Every incident keeps its original evidence, hypotheses, user actions and verification results. Export to Markdown or JSON.

### F13. Dashboard
Local web UI with: overview, incidents, incident case file, pipeline and dependency map, scan results, evaluation results, settings. See UI_UX_DESIGN_BRIEF.md.

### F14. Benchmark harness
`faultsage bench` runs FaultSage on real benchmark cases and writes a run record (dataset version, case list, seeds, metrics, failures). This is how every number in the README is produced.

### F15. Self-monitoring
FaultSage records its own uncaught errors into a separate local incident log, so its own bugs are triaged with its own tool.

---

## 6. MVP scope

### In scope (first release)

| # | Item |
|---|---|
| 1 | Python 3.11+ projects, on Windows (PowerShell) and Linux |
| 2 | `pip install` from the repository (PyPI publishing later) |
| 3 | `init`, `watch`, `pause`, `stop`, `scan`, `run`, `verify`, `apply`, `dashboard`, `bench`, `purge` |
| 4 | Signals: pytest results, uncaught exceptions via `faultsage run`, configured log files, git changes, declared pipeline checkpoints |
| 5 | Incident grouping by signature |
| 6 | Evidence-based ranking with certainty labels |
| 7 | File, line and function localisation where available |
| 8 | Import graph and declared pipeline graph |
| 9 | Blast radius with known vs inferred labels |
| 10 | Rule-based fix suggestions with patch preview |
| 11 | Approval-gated apply with backup |
| 12 | Verification by rerunning failing and affected tests |
| 13 | Local dashboard with incident case file and graph |
| 14 | SQLite incident history and Markdown/JSON export |
| 15 | Benchmark harness for BugsInPy (main) and JunoBench, LogSage or LogChunks (second stage) |
| 16 | One registered project at a time |

### Out of scope (later)

- Multi-project command centre
- JavaScript, TypeScript, Java support
- Automatic code changes without approval
- Hosted or multi-user deployment, accounts, teams
- Distributed tracing across services
- Model drift and bias monitoring
- Predictive anomaly detection

---

## 7. Success metrics

No number below is a result. They are targets, and each is reported only after a recorded benchmark run (see TESTING.md, section on run records). Accuracy targets are stated relative to baselines because absolute numbers on real bugs are unknown until measured.

### Diagnosis (measured on the held-out split of real benchmark cases)

| Metric | Definition | Target |
|---|---|---|
| File Top-1 / Top-3 / Top-5 | True buggy file (from the developer's real fix) appears in the top k | Beats the best baseline (top stack frame, Ochiai, recently changed) on Top-3 |
| Function Top-1 / Top-3 / Top-5 | Same at function level | Reported with baselines; no fixed target |
| Ablation | Change in Top-3 when each evidence source is removed | Reported for every source |
| Abstention honesty | Share of incidents where FaultSage says "Unknown" and the top candidate was in fact wrong | Reported |

### Blast radius

| Metric | Definition | Target |
|---|---|---|
| Test precision / recall | Predicted affected tests vs tests that actually fail on the buggy version | Recall higher than "every test importing the file" baseline at equal or better precision |

### Fixes and verification

| Metric | Definition | Target |
|---|---|---|
| Verification correctness | On the developer's real fix, does `verify` report "resolved" and on the buggy version "still failing" | 100% of reproducible cases, any miss is a bug |
| Rule patch success | Share of rule-generated patches that make the failing test pass without breaking passing tests | Reported honestly, no target |
| Usefulness | Testers rate recommendations useful (1 to 5) | At least 4.0 average from at least 8 testers, raw scores published |

### Product

| Metric | Target |
|---|---|
| `init` to first monitored test run | Under 60 seconds on a mid-range laptop |
| Detection delay (pytest finishes to incident visible) | Under 2 seconds, median |
| Watch daemon idle CPU / memory | Under 2% CPU, under 200 MB |
| Stability | 8-hour watch session with no crash |
| Zero writes without approval | 0 unapproved writes in all tests (hard requirement) |

---

## 8. Acceptance criteria

| ID | Criterion | How it is checked |
|---|---|---|
| AC1 Install | `pip install -e .` then `faultsage --help` works on Windows PowerShell and Ubuntu (WSL2) | CI on Ubuntu, manual on Windows, recorded |
| AC2 Connect | `faultsage init` in a real project lists detected source, tests, dependency files and git, and writes config | Integration test on a real BugsInPy checkout |
| AC3 Watch controls | `watch`, `pause`, `stop` change state, and the dashboard shows the state within 1 second | Integration test |
| AC4 Detect | A real failing test in a BugsInPy bug creates one incident with the traceback | Integration test |
| AC5 Locate | Incident shows file, line, function and code excerpt, or "line not available" | Unit and integration tests |
| AC6 Rank | Incident shows ranked hypotheses, each with evidence items and a certainty label | Integration test, schema validation |
| AC7 Blast radius | Graph shows known and inferred dependencies; affected tests listed | Integration test on real repo |
| AC8 Fix guidance | Recommendation has explanation, evidence, patch preview or "no safe patch", and a verify command | Unit tests per rule |
| AC9 Safe apply | No file changes without approval; apply creates backup and approvals record; dirty git tree blocks apply | Tests that assert file hashes are unchanged |
| AC10 Verify | After applying the developer's real fix, `verify` reports resolved; on buggy version, still failing | Benchmark integration test |
| AC11 Dashboard | Overview, incidents, case file, graph, settings render with real data, keyboard usable, WCAG 2.2 AA checks pass | Playwright + axe-core, screenshots saved |
| AC12 History | Past incidents with actions and verification can be opened and exported | Integration test |
| AC13 Stability | 8-hour watch session, resource use logged | Soak test record |
| AC14 Transparency | Every claim in the UI carries Confirmed, Strong, Possible or Unknown | UI test + review |
| AC15 Benchmarks | `faultsage bench` produces a run record that reproduces published numbers from the same inputs | Rerun check |
| AC16 Local only | No outbound network calls during watch, scan, verify or dashboard use | Test with network blocked |

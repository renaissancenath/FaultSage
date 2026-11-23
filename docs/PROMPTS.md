# FaultSage: Prompt Templates

Every task given to an AI coding agent uses four parts. Missing parts mean the agent should ask before coding.

```markdown
## Context
- Project: FaultSage (read AGENTS.md first)
- Stage: <1 to 8 from AGENTS.md section 9>
- Requirement IDs: <FR-xx, NFR-xx, SR-xx>
- Relevant docs: <files>
- Current state: <what exists, what passes>

## Task
<one clear outcome, e.g. "Implement the pytest plugin that writes test_result events to the spool">

## Constraints
- Free and open-source dependencies only; no new dependency without asking
- Windows PowerShell commands for me; WSL2 for benchmarks
- No writes to monitored project files; no shell=True; bind 127.0.0.1
- Real data only for any metric; fixtures recorded from real cases with provenance
- Check installed library versions before using an API
- Ask (DECISIONS.md) for anything in a decision category

## Expected output
- Plan paragraph first, then code
- Files created or changed (exact paths)
- Tests added and the command to run them
- What I should see when it works (exact output or screenshot)
- What is not done yet
```

---

## Stage prompts

### Stage 1: skeleton, spool, plugin, first real case
**Task:** Create the package skeleton (`src/faultsage`, `pyproject.toml` with `[project.scripts] faultsage = "faultsage.cli.main:app"` and `[project.entry-points.pytest11] faultsage = "faultsage.collectors.pytest_plugin"`), config models, spool writer, pytest plugin, `faultsage init`, `faultsage run`. Then in WSL2, a script that fetches BugsInPy, checks out one pandas bug in a container, runs its failing test with the plugin, and copies the spool out.
**Expected output:** `faultsage --help` works on PowerShell; one real spool file from a BugsInPy pandas case committed under `tests/fixtures/bugsinpy/pandas-<id>/` with PROVENANCE.md.

### Stage 2: localisation engine and baselines
**Task:** Traceback parser, AST index, candidate builder, baselines (random, top frame, recently changed), metrics (Top-k, EXAM), `bench run` on the dev split for pandas, luigi, keras.
**Expected output:** First `results/runs/<id>/run.json` on dev, with attempted, reproduced and excluded counts.

### Stage 3: daemon and incidents
**Task:** Daemon lifecycle, ingest, SQLite migrations 0001, grouping, CLI `watch/status/pause/resume/stop/incidents/show`.
**Expected output:** Run `pytest` in a real BugsInPy checkout with `faultsage watch` running; `faultsage incidents` shows one incident.

### Stage 4: graphs and blast radius
**Task:** Import graph, pipeline graph, checkpoints, blast radius, blast-radius metrics vs "all importers" baseline.
**Expected output:** Dev run record with blast-radius precision and recall.

### Stage 5: coverage, ranker, certainty
**Task:** Coverage contexts, Ochiai, feature vector, logistic regression on dev, certainty calibration, ablation table; then one test-split run.
**Expected output:** `weights.json` with run id; test-split run record.

### Stage 6: fixes, approval, verify
**Task:** Rule library (FR-22), patch builder, apply gate, verify runner. Verify correctness on buggy and fixed commits.
**Expected output:** Tests for every rule; verify correctness record on reproduced cases.

### Stage 7: API and dashboard
**Task:** FastAPI routes and auth (02_LOGIN-RULES.md), WebSocket, React app with screens from UI_UX_DESIGN_BRIEF.md, using the faultsage-design skill.
**Expected output:** Playwright screenshots of every screen at 4 widths, light and dark; axe clean; slop check clean.

### Stage 8: more datasets and release
**Task:** JunoBench and LogSage/LogChunks adapters, Evaluation screen, README results from test run, launch checklist.
**Expected output:** Release PR with completed 05_LAUNCH-CHECKLIST.md.

---

## Triage prompt (production-only bug)

```markdown
## Context
FaultSage self-monitoring captured this error (redacted): <paste internal incident export>
Version: <x.y.z>, OS: <...>, command: <...>

## Task
Find the most likely cause, write a failing test that reproduces it from the captured data, then propose the smallest fix.

## Constraints
No behaviour change outside the bug. No new dependencies. Follow AGENTS.md.

## Expected output
Root cause with evidence, the failing test, the fix, all checks passing, a PR for human review.
```

## Review prompt (agentic PR review)

```markdown
## Context
PR #<n> for FaultSage. Diff attached. Requirement IDs: <...>.

## Task
Review for: correctness against the requirement, missing tests, security rules SR-1 to SR-28, writes outside apply gate, invented APIs (check installed versions), design rules and slop check for UI, doc drift.

## Constraints
Report findings as file:line with severity (blocker, should fix, nit). Do not rewrite the PR.

## Expected output
A findings list and a one-line verdict: approve, approve with fixes, or request changes.
```

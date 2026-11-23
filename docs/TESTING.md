# FaultSage: Testing and Evaluation

Two separate things:
1. **Software tests** prove FaultSage behaves as specified.
2. **Evaluation** measures how well it diagnoses real bugs. Only evaluation produces accuracy numbers.

## 1. Real-data rule

- No synthetic data, injected faults or invented projects appear in any reported metric.
- Test fixtures are recorded from real runs (BugsInPy, JunoBench, LogSage, LogChunks cases, or real open-source projects). Each fixture folder has `PROVENANCE.md`: dataset, case id, dataset version, command used to record it, date.
- Small hand-written inputs are allowed only for parser edge cases that real data does not cover (for example an empty traceback), and must be named `edge_*` with a comment. They never feed metrics.

## 2. Test layers

| Layer | Location | Tools | What |
|---|---|---|---|
| Unit | `tests/unit/` | pytest, hypothesis | Parser, AST index, graph, Ochiai, features, certainty, redaction, patch building, path checks |
| Contract | `tests/contract/` | pytest + Pydantic | Spool events, API responses match BACKEND_SCHEMA.md; OpenAPI snapshot |
| Integration | `tests/integration/` | pytest, real checkouts | init, plugin, daemon ingest, incident grouping, scan, apply gate, verify on a real BugsInPy case |
| Security | `tests/security/` | pytest | Host and Origin checks, token flow, path escape, symlink escape, XSS strings render as text, no `shell=True`, no writes outside gate |
| Frontend unit | `web/src/**/*.test.tsx` | Vitest | Components and state rendering |
| End to end | `web/e2e/` | Playwright + axe-core | Screens with real recorded data, keyboard paths, accessibility, screenshots |
| Soak | `tests/soak/` | psutil | 8-hour watch session resource record |
| Benchmark | `faultsage bench` | containers | Evaluation (section 5) |

## 3. Must-have tests

| Area | Test |
|---|---|
| Plugin safety | Plugin raising internally does not change pytest exit code or output |
| Spool | Concurrent writers, rotation, partial last line recovery |
| Ingest idempotence | Re-reading the same spool file creates no duplicates |
| Grouping | Same signature appends occurrence; resolved incident reopens on recurrence |
| Traceback parser | Chained exceptions, pytest long and short formats, Windows paths, non-UTF-8 bytes |
| Location honesty | Missing source gives `available: false`, never a guessed line |
| Certainty | Unknown when fewer than the required evidence sources |
| Write gate | Hash every project file before and after all non-apply tests; must be identical |
| Apply gate | Stale hash refused; dirty tree refused; failure restores backup; approval row written |
| Verify | On BugsInPy fixed commit returns resolved; on buggy commit returns still_failing |
| Redaction | AWS-style keys, GitHub tokens, `password=`, `.env` values, bearer tokens are masked |
| Network | Runtime commands make zero outbound connections (socket monkeypatch + CI job with network off) |

## 4. Coverage targets

- `analysis`, `fixes`, `storage`, `api`: 85% line coverage, 75% branch.
- Coverage is a floor, not a goal. Missing tests for a requirement ID block merge regardless of percentage.

## 5. Evaluation protocol

1. Datasets and splits as in DATASETS.md. Split file committed before tuning.
2. All tuning (feature weights, Strong threshold, rule tweaks) on **dev** only.
3. **Test** split run once per release tag. If code changes after a test run, the next test run gets a new run id; old runs stay in `results/runs/`.
4. Each case runs in a fresh container, network disabled after install, fixed seed, timeout per case.
5. Per case record: reproduced or not (reason), ground truth, predictions from FaultSage and every baseline, blast-radius sets, verify results.
6. Metrics computed by `bench/metrics.py` from `cases.jsonl` only, so anyone can recompute them.
7. Report: attempted, reproduced, excluded by reason, metrics with 95% bootstrap confidence intervals, baselines in the same table, ablation table, list of worst failures with notes.
8. README and resume numbers are copied from a test-split `run.json` with the run id. Never rounded up, never from dev split.

### Metrics definitions

| Metric | Definition |
|---|---|
| Top-k (file or function) | 1 if any ground-truth file or function is in the top k predictions, averaged over reproduced cases |
| EXAM | Rank of the first ground-truth function divided by number of candidate functions (lower is better) |
| Blast precision / recall | Over tests: predicted affected vs tests failing on the buggy version |
| Verify correctness | Share of cases where verify says still_failing on buggy and resolved on fixed |
| Rule patch success | Share of rule patches after which the failing tests pass and previously passing tests still pass |
| Detection rate | Share of reproduced cases where an incident was created |
| Abstention honesty | Among cases labelled Unknown, share where top-1 was actually wrong |

### How a BugsInPy case runs (D-023)

1. The buggy and fixed commits are checked out on the host. As in BugsInPy's own checkout, the bug's test files come from the fixed commit.
2. In a container with network on: a venv with the bug's pinned requirements (pip-freeze artifacts that cannot install on Linux, such as `pywin32` and `pkg-resources==0.0.0`, and the line that installs the project itself, are removed), then each checkout is installed and its `setup.sh` runs.
3. With network off: the developer's failing test command runs on both checkouts. Reproduced means the buggy run fails and the fixed run passes.
4. On the host: FaultSage parses the buggy run's traceback (pytest runs use `--tb=native`) and analyses the checkout and its git history. Baselines use the same inputs. Test files are removed from every method's ranking because the ground truth never contains them.
5. If the container engine itself stops, the run aborts instead of recording cases as excluded.

Run with `faultsage bench run bugsinpy --split dev`, train with `faultsage bench train <dev run id>`, then run the test split once.

## 6. UI checks and screenshots

- Playwright scripts load recorded real cases into a test daemon and capture each screen at 1440, 1024, 768, 375 px, light and dark, into `web/test-results/screens/`.
- axe-core: zero serious or critical violations.
- `tools/slop_check.py` and `--contrast` must pass.
- The agent and the reviewer look at the screenshots before approving UI PRs.

## 7. Running tests

```powershell
pytest -q                                  # unit + contract + security
pytest -q tests/integration -m "not slow"  # needs git
pytest -q -m slow                          # needs WSL2 + Docker Engine
cd web; npm test; npx playwright test; cd ..
python tools/slop_check.py; python tools/slop_check.py --contrast
```

## 8. Manual checks before a release

- Fresh Windows machine: install, init, watch, fail a real test, apply, verify. Record with screenshots.
- Keyboard-only pass through every screen.
- Read every UI string once for clarity and banned words.

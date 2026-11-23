# AGENTS.md: How to work on FaultSage

Read this whole file before writing code. It applies to every AI coding agent and to humans.

---

## 1. Project context and purpose

FaultSage is a free, local Python tool. It watches a Python project (pytest results, uncaught exceptions, logs, git changes, declared pipeline steps), and when something fails it ranks likely root causes with evidence, points to the file and line, maps the blast radius, suggests a patch behind an approval gate, and verifies the fix by rerunning tests. A local dashboard shows it all.

It is a portfolio and research project for Renaissance Nath (B.Tech AI and Data Science). Its value depends on two things being true:

1. **It actually works** on real projects (no mockups presented as features).
2. **Its numbers are real**: every accuracy figure comes from a recorded run on real bug benchmarks (BugsInPy, JunoBench, LogSage, LogChunks) against baselines. No synthetic or demo data in any reported metric.

The engineer is a beginner-to-intermediate developer on **Windows PowerShell**, with WSL2 Ubuntu for benchmarks. Explain what you do in plain language and give exact commands.

## 2. Before you start

Read, in this order:
1. `docs/PRD.md`: what and why.
2. `docs/ARCHITECTURE.md`: structure and dependency rules.
3. `docs/TRD.md`: requirement IDs you will implement.
4. `docs/DECISIONS.md`: decided items and the open questions queue.
5. The doc for your area: `BACKEND_SCHEMA.md`, `DATABASE.md`, `DESIGN_SYSTEM.md` + `.agents/skills/faultsage-design/SKILL.md` for UI, `TESTING.md`, `docs/security/`.

Then:
- Run `git status` and the test suite to know the starting state.
- Check installed versions (`python -m pip show <pkg>`, `npm ls <pkg>`) before using any library API.
- State in one paragraph: the requirement IDs you are implementing, the files you expect to touch, and how you will test it. Wait for a go-ahead if any item touches a decision category in section 11.

## 3. General rules and working rules

1. Work in small slices. One requirement or one bug per pull request.
2. Never present planned features as working. If something is a stub, it says so in code (`NotImplementedError` with the requirement ID) and in the PR.
3. Never invent numbers, benchmark results, line numbers, file paths, API methods or library options. If unsure, check the installed source or official docs (section 3.1).
4. Never write to the monitored project's files outside `fixes/apply_gate.py`.
5. Never run destructive commands (deleting files or tables, `git reset --hard`, `git push --force`, dropping data) without explicit human approval for that exact command, every time (section 5, approval gate).
6. Ask instead of guessing for anything in the decision categories (section 11). Put the question in `docs/DECISIONS.md` under "Open questions" and wait.
7. Free and open source only. No paid APIs, API keys, accounts, trials or quota-limited services. A new dependency needs a row in TRD.md section 2 and a decision entry.
8. Keep docs and code in sync. If behaviour changes, update the doc in the same PR.
9. Leave the repository runnable after every commit.

### 3.1 Use real, current documentation (MCP)
Code against the API that is actually installed, not the one you remember.

- Use the free, open-source reference MCP servers:
  - `fetch` (`mcp-server-fetch`, MIT) to read official docs pages: docs.python.org, docs.pytest.org, fastapi.tiangolo.com, docs.pydantic.dev, typer.tiangolo.com, networkx.org, coverage.readthedocs.io, reactflow.dev, vite.dev, react.dev.
  - `git` (`mcp-server-git`, MIT) to read history and diffs.
  - `filesystem` (MIT) limited to this repository.
- Before calling an unfamiliar method, confirm it exists in the installed version: read the package source in the virtualenv or run `python -c "import pkg, inspect; print(inspect.signature(pkg.func))"`.
- If the docs and installed version disagree, the installed version wins. Pin it and note it in the PR.
- Do not use paid or quota-based documentation services.

### 3.2 Prompts you receive
Prompts follow `docs/PROMPTS.md`: context, task, constraints, expected output. If a prompt is missing one of these, ask for it before coding.

## 4. Code guidelines

- Python 3.11+, type hints everywhere, `from __future__ import annotations`.
- Ruff for lint and format, mypy strict for `analysis`, `fixes`, `storage`, `api`.
- Pydantic v2 models for every boundary (spool, API, config, bench records).
- Pure functions in `analysis`. No I/O there except through passed-in readers.
- All SQL in `storage/`, parameterised, never f-strings.
- Subprocess with argument lists, `shell=False`, timeouts, and `check=False` with explicit handling.
- Errors: raise specific exceptions from `faultsage.errors`; messages say what failed and what to do.
- Frontend: TypeScript strict, React function components, CSS Modules on `design/tokens.css`, no component kits, no inline hex colours.

### 4.1 Design skills for UI work
Load `.agents/skills/faultsage-design/SKILL.md` first; it overrides any other skill on tokens and rules. Then use these free, open-source skills in this order (install from their public repositories and check each licence before use):

1. **Frontend Design**: set a bold, specific direction inside our case-file concept.
2. **Taste Skill** and **UI UX Pro Max**: art direction and style choices, constrained to our tokens and fonts.
3. **Impeccable** (Paul Bakaus): critique, audit, polish; catch slop.
4. **Web Design Guidelines** (Vercel): review UI code before merge, with file and line findings.

Then run `tools/slop_check.py` and the Playwright screenshots, and look at them.
- Full conventions in `docs/CODE_STYLE.md`.

## 5. Security and best practices

Full rules in `docs/security/01_SECURITY-RULES.md`. The ones agents break most often:

1. Bind the server to `127.0.0.1` only. Never `0.0.0.0`.
2. No `shell=True`, `eval`, `exec`, `pickle.load` on untrusted data, `yaml.load` without SafeLoader.
3. Redact secrets with `faultsage.redact` before anything is stored or shown.
4. Render tracebacks, logs and code as text. Never `dangerouslySetInnerHTML`.
5. Paths from users, configs or patches are resolved and must stay inside the project root.
6. Benchmark repositories are untrusted code: run them only in containers with network off after install.

### Destructive and write actions: human approval gate
| Action | Rule |
|---|---|
| Write to monitored project files | Only via apply gate, after an approval record from the user |
| Delete or overwrite any file outside `.faultsage/` | Ask, show exact paths, wait for "yes" for that call |
| Database migration that drops, renames or deletes (`DROP`, `DELETE`, `ALTER ... DROP`, table rebuild) | Write the migration, show it, explain data impact, make a backup step part of it, wait for approval. Never run it on the engineer's real data without approval for that specific run. |
| `git push`, force operations, branch deletion, history rewrite | Never without explicit instruction |
| Installing global tools or changing system settings | Ask first |

Approval for one destructive call never carries over to the next. "Clean up unused tables" means: propose a migration, show the list, wait.

## 6. Useful commands

```powershell
# Setup (Windows PowerShell)
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
cd web; npm ci; cd ..

# Checks (same as CI)
ruff check .
ruff format --check .
mypy src
pytest -q
python tools/slop_check.py
python tools/slop_check.py --contrast
bandit -q -r src -c pyproject.toml
pip-audit --skip-editable
cd web; npm run lint; npm run typecheck; npm test; npm run build; cd ..
bash tools/e2e_screens.sh    # WSL2/Linux: screenshots + axe in web/test-results/screens
.\tools\ci_local.ps1         # everything above in one go

# Run locally
faultsage init
faultsage watch
faultsage-cloud serve        # hosted part, see docs/DEPLOY.md

# Benchmarks (inside WSL2 Ubuntu with Docker Engine)
faultsage bench fetch bugsinpy
faultsage bench run bugsinpy --split dev --projects pandas luigi keras
```

Commands for parts not built yet will fail until the matching stage is done. That is expected; do not fake them.

## 7. Need help?

- If a requirement is unclear: add it to "Open questions" in `docs/DECISIONS.md` with options and your recommendation, then stop that part.
- If a library behaves differently from docs: write the observation and installed version in the PR, choose the safe behaviour.
- If tests are flaky: do not retry until green. Find the cause or mark it with an issue and owner.
- If you are stuck for more than two attempts on the same error: stop and report what you tried, the exact error and your best hypothesis.

## 8. Source of truth

When documents disagree, this order wins:

1. Code and tests that currently pass on `main` (for current behaviour).
2. `docs/DECISIONS.md` decided entries.
3. `docs/TRD.md` requirement IDs.
4. `docs/PRD.md`.
5. `docs/ARCHITECTURE.md`, `BACKEND_SCHEMA.md`, `DATABASE.md`.
6. `docs/DESIGN_SYSTEM.md` + `design/tokens.css` (tokens file wins on values).
7. Everything else.

Benchmark claims: only `results/runs/*/run.json` files count. README numbers must be copied from them with the run id.

## 9. Workflow

1. Pick a requirement ID (or bug) and create a branch `feat/FR-12-incident-grouping` or `fix/<short-name>`.
2. Write the plan paragraph (section 2).
3. Write or update tests first where practical.
4. Implement the smallest change that passes.
5. Run all checks in section 6.
6. For UI: run screen screenshots and look at them; follow the design skill workflow.
7. Update docs touched by the change.
8. Open a PR using `.github/pull_request_template.md`. CI must pass. The engineer reviews and merges. Agents never merge their own PRs.

Build stages (do not skip ahead):

| Stage | Deliverable |
|---|---|
| 1 | Package skeleton, config, spool, pytest plugin, `faultsage run`; BugsInPy fetch and one reproduced case end to end in a container |
| 2 | Traceback parser, AST index, candidates, baselines, metrics; first dev-split run record |
| 3 | Daemon, SQLite, incident grouping, CLI `watch/status/incidents/show` |
| 4 | Import graph, pipeline graph, checkpoints, blast radius; blast-radius metrics |
| 5 | Coverage contexts and Ochiai, trained ranker, certainty labels; test-split run |
| 6 | Fix rules, patch preview, apply gate, verify runner |
| 7 | API and dashboard screens with screenshots |
| 8 | JunoBench and LogSage/LogChunks adapters, evaluation page, docs and release |

## 10. Validation checklist

Before saying "done":
- [ ] Requirement IDs listed in the PR and each has a test or a recorded manual check.
- [ ] `ruff`, `mypy`, `pytest`, `bandit`, `pip-audit` pass.
- [ ] Web: lint, typecheck, unit tests, build, Playwright and axe pass (if web touched).
- [ ] `tools/slop_check.py` and `--contrast` pass.
- [ ] Screenshots attached for UI changes, and you looked at them.
- [ ] No writes to monitored project files outside the apply gate (test passes).
- [ ] No new network calls at runtime.
- [ ] No invented numbers; any metric links to a run record.
- [ ] Docs updated.
- [ ] Destructive steps, if any, were approved for that specific call and the approval is quoted in the PR.

## 11. Conflict handling and who decides

The agent does not decide these by default. It asks, records the question, and waits:

| Category | Examples |
|---|---|
| Architecture | New process, new package boundary, queue, changing spool format |
| Data and database | Schema changes, migrations, retention, anything destructive |
| Auth and security | Token handling, binding address, CORS, redaction rules |
| Dependencies | Adding, removing or upgrading a major version |
| Scope | Features outside the current stage or PRD |
| Evaluation | Splits, metrics definitions, excluding cases |
| UI direction | New screen, changing tokens, breaking a design rule |

How to ask: add an entry to `docs/DECISIONS.md` "Open questions" with context, options, trade-offs, recommendation, and what is blocked. The engineer answers; the answer becomes a numbered decision. Then build.

If two docs conflict, follow section 8, then propose a doc fix in the same PR.

## 12. Definition of done

A change is done when:
1. It does what the requirement says on a real project or real benchmark case, not only in a unit test.
2. All checks in section 10 pass.
3. Docs match the behaviour.
4. The engineer can run it from a fresh clone with the commands in section 6.
5. Any claim it enables (in README or resume) is backed by a run record or a reproducible demo on real data.

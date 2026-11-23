# FaultSage: Decisions and Open Questions

This file is how "who decides" works. The engineer decides; agents ask.

## How it works

1. An agent hits something in a decision category (AGENTS.md section 11): auth, database, schema, dependencies, scope, evaluation, UI direction, anything destructive.
2. It does **not** pick a default. It adds an entry under **Open questions** with context, options, trade-offs, its recommendation, and what is blocked. It continues only with unblocked work.
3. The engineer answers. The answer moves to **Decided** with the next D-number and date.
4. Decided entries are followed until replaced by a newer decision that names the one it replaces.

---

## Decided

| ID | Date | Decision | Why | Replaces |
|---|---|---|---|---|
| D-001 | 2026-11-23 | FaultSage is a local, single-user tool: CLI + local dashboard. No hosted SaaS in v1. | Privacy, zero cost, fits the problem | |
| D-002 | 2026-11-23 | Python projects only in v1 | Scope | |
| D-003 | 2026-11-23 | Storage: SQLite per project, WAL mode | Zero setup, enough for one user | |
| D-004 | 2026-11-23 | Auth: 127.0.0.1 bind + one-time token + HttpOnly SameSite=Strict cookie + Host/Origin checks. No accounts. | Local threat model | |
| D-005 | 2026-11-23 | Collectors write to a spool folder; daemon ingests | Tests never depend on daemon | |
| D-006 | 2026-11-23 | Evaluation only on real bugs: BugsInPy (main), JunoBench, LogSage, LogChunks. No synthetic data in metrics. OpenRCA dropped from this project (no code, tests or fixes). | Resume claims must be real | |
| D-007 | 2026-11-23 | Split by project; tune on dev, report on test once per release | Avoid leakage | |
| D-008 | 2026-11-23 | Only free, open-source dependencies with no paid tier needed. CI on a public GitHub repo; local CI scripts as fallback. | Cost and independence | |
| D-009 | 2026-11-23 | UI: own components on tokens, IBM Plex Sans/Mono, Phosphor icons, React Flow core, no component kit | Avoid template look | |
| D-010 | 2026-11-23 | Code licence: MIT | Simple, permissive | |
| D-011 | 2026-11-23 | No automatic code changes; every write via approval gate with backup | Safety | |
| D-012 | 2026-11-23 | Fix suggestions are rule-based; optional local model via Ollama, off by default | Free, local, explainable | |
| D-013 | 2026-11-23 | Benchmarks run in Docker Engine or Podman inside WSL2, not Docker Desktop | Free, isolation | |
| D-014 | 2026-11-23 | Product shape is hybrid: the free local CLI/daemon keeps all analysis, apply gate and verify on the user's machine; an optional hosted service (FaultSage Cloud) adds accounts, synced redacted case files, production error ingest and triage. | Engineer: "whichever is free and helps the requirements work". Keeps the privacy model and adds a sellable hosted part | D-001 |
| D-015 | 2026-11-23 | Cloud auth: email + password (Argon2id, rules in 02_LOGIN-RULES.md section 4) with email verification and reset over any SMTP server, plus optional GitHub OAuth enabled only when its env vars are set. Local dashboard auth stays as D-004. | Engineer: "free". Both cost nothing | D-004 (cloud only) |
| D-016 | 2026-11-23 | Cloud storage: PostgreSQL in production (Neon or Render free tier), SQLite for local cloud development and tests, accessed through SQLAlchemy Core with parameterised SQL in `faultsage/cloud/storage/` only. Local daemon stays on SQLite (D-003). | Engineer: "free". Postgres free tiers exist; one code path | |
| D-017 | 2026-11-23 | Plans: Free and Pro with enforced limits (projects, events per month, retention, seats). No payment provider is wired by default; the upgrade flow records interest. A billing adapter interface exists so a provider (Lemon Squeezy recommended for a seller in India) can be added by a later decision. | Engineer: "free one". No cost until a provider is chosen | |
| D-018 | 2026-11-23 | Deployment: one Docker image (FastAPI serving the built React app) with `render.yaml` (free web service) and `docker-compose.yml` (any VPS, with Postgres and Caddy for HTTPS). | Engineer: "free". Portable, no vendor lock | |
| D-020 | 2026-11-23 | CSP adds `style-src-attr 'unsafe-inline'` (inline style attributes only). `style-src`, `script-src` stay `'self'`. Needs engineer confirmation: see Q-007. | React Flow sets node positions with inline style attributes; without this the graph renders broken. No `<style>` elements or scripts are allowed. | SR-5 (narrowed exception) |
| D-021 | 2026-11-23 | Two tokens added to tokens.css: `--fs-scrim` (ConfirmDialog backdrop) and `--fs-inset-rule` (active state). | DESIGN_SYSTEM section 11 asks for a 1 px inset active rule and a dialog overlay; both needed a token instead of raw values. | |
| D-022 | 2026-11-23 | BugsInPy split v1 (`src/faultsage/bench/splits/bugsinpy_v1.json`): dev = pandas, keras, luigi, black, tqdm, httpie, sanic (7 of 17 projects); test = the other 10. Answers Q-002 with option 2. | Engineer: "do all this". Dev and test each hold data, ML and web code; split by project so the test projects are never seen while tuning | |
| D-023 | 2026-11-23 | Benchmark collection runs no FaultSage code inside the case container: the container runs only the developer's failing test command (network off) and FaultSage parses the captured traceback on the host, like `faultsage run`. | BugsInPy needs Python 3.6 to 3.8 and many cases use unittest, so an in-container pytest plugin cannot cover them; this works for every case | |
| D-019 | 2026-11-23 | D-008 amended for the cloud: still only free, open-source libraries; the hosted service may run on free tiers of hosting providers. The local tool still makes no network calls unless the user runs `faultsage cloud push` or enables cloud sync. | Hosting cannot be fully self-contained | D-008 (partly) |
| D-024 | 2026-11-23 | The "Strong" certainty is withheld: shipped `weights.json` has `strong_enabled: false`, so the top cause is labelled at most Possible. Evidence and ranking are unchanged. Training (`faultsage bench train`) always writes `false`; only a person may set it back to `true`, and only after a new held-out test run (new run id) shows Strong precision of at least 0.75. Answers Q-009 with option 3. | Engineer: "Hide the unreliable Strong confidence label". Test run 090824: Strong right on 1 of 8 | |
| D-025 | 2026-11-23 | Billing provider: Lemon Squeezy (merchant of record) through the existing webhook adapter, kept off (`BILLING_PROVIDER=none`) until the launch checklist in DEPLOY.md is complete. Plan changes come only from signed `subscription_*` events that carry a subscription object; `cancelled` keeps Pro until `expired`; events older than the last applied one are ignored (`orgs.billing_updated_at`, migration 0002). Paddle (also merchant of record) is the fallback if Lemon Squeezy does not pay out to your country. Answers Q-004 with option 1. | A merchant of record collects and files sales tax/GST/VAT worldwide, which a single beginner seller cannot do safely; no monthly fee | |
| D-026 | 2026-11-23 | Product architecture confirmed: one hosted multi-tenant SaaS (FaultSage Cloud: registration, login, workspaces, free plan) plus the open-source local CLI as its client. Tenancy is a shared PostgreSQL database with an `org_id` on every tenant row; every query in `cloud/storage/repo.py` filters by the caller's org (projects) or by a project already checked to belong to it; a test (`tests/cloud/test_isolation.py`) calls every route with another tenant's ids. No separate database per customer. Code analysis stays on the user's machine; the cloud stores redacted tracebacks and case files only. | Cheapest safe option: one free database, one app; per-tenant databases cost more and do not fit free tiers. Keeping source code off the server shrinks what a breach could expose | |
| D-027 | 2026-11-23 | Q-003 answered: public repository (free Actions minutes, portfolio). Q-005 answered: keep the Free limits (2 projects, 5,000 events/month, 14 days, 1 seat). Q-007 answered: keep D-020. | Engineer asked for decisions to be resolved with safe, affordable defaults | |
| D-028 | 2026-11-23 | Security fixes from the stage-2 review: (a) GitHub sign-in that matches an account whose email was never confirmed removes that account's password and sessions before linking (pre-account hijacking); (b) inviting a member gives the same reply and sends an email whether or not the address has an account (no account enumeration); (c) the reanalyse command writes its run record through `bench/runner.write_run`, so the Semgrep write rule passes in CI. | Found while writing the isolation and session tests | |
| D-029 | 2026-11-23 | Backup and restore: `faultsage-cloud db backup` (any time) and `faultsage-cloud db restore` (destructive: typed `restore <file> on <env>`, named approver, file checked first, safety backup of current data, one transaction, recorded in `migration_approvals` with version -1). The image ships pg_dump, pg_restore and psql 17; the restore drops pg_dump 17's `SET transaction_timeout` line so it also works on PostgreSQL 16 servers. Backup names include microseconds and are created exclusively. Database commands need only `DATABASE_URL` and `FAULTSAGE_ENV`. | Engineer: "Complete database migrations and backup/restore". Verified in the production image against PostgreSQL 16 | |
| D-030 | 2026-11-23 | Synced case files carry no source code: `faultsage cloud push` drops code excerpts (`excerpt`) and patch diffs (`patch_diff`) before sending, and the server drops them again on ingest. The cloud view says the patch stays on the user's machine. Production tracebacks keep their one line of code per frame, and the privacy notice now says so. | The end-to-end run showed a synced case file displaying source lines, contradicting the privacy notice ("We do not collect your source code") and D-026. The behaviour was changed to match the promise, not the other way round | |
| D-031 | 2026-11-23 | Behind a proxy, the client IP for rate limits is the X-Forwarded-For entry `FAULTSAGE_PROXY_HOPS` places from the right (default 1: Render, Caddy), never the leftmost entry. | The leftmost entry is sent by the visitor, so anyone could bypass login, sign-up and reset-email rate limits by sending a fake header. Found while preparing the deployment | |
| D-032 | 2026-11-23 | Open core. The public repository holds the CLI, daemon, local dashboard, cloud service, web app, benchmark harness, results and docs, under an all-rights-reserved licence (supersedes D-010, MIT). The ranking engine (candidate features and scoring), trained weights, full fix-rule library and training code move to the private package `faultsage_engine`. The public package loads it when installed and otherwise runs `analysis/basic.py` (traceback-only ranking, same output shape) with three simple public rules. Public CI runs without the engine and skips 6 tests that check the engine's specific answers; the private repository's CI runs its own tests and the whole public suite with the engine. | Engineer: protect the "secret sauce" while recruiters can see the system. Anything installed on a customer's machine can be read, so the engine stays out of the public package; how paying customers receive it is Q-011 | D-010 |
| D-033 | 2026-11-23 | Vendor-neutral tooling: the AI pull-request review is `ai-review.yml` + `tools/ai_review.py` and works with any OpenAI-compatible chat API (`AI_REVIEW_API_KEY` secret, `AI_REVIEW_BASE_URL` and `AI_REVIEW_MODEL` variables); without them it passes and skips. No product or company name of an AI vendor appears in the repository. | Engineer: keep the AI features with neutral names | |
| D-034 | 2026-11-23 | CI stays green on a fresh repository: `.gitleaks.toml` allows the fake secrets in `tests/`, `web/e2e/`, `docs/` and `.env.example` (gitleaks 8.21.2 found 3 without it, 0 with it); `bug-inbox.yml` skips before installing anything when no mailbox is configured; `tools/breakout.sh` no longer expects a Strong label (withheld since D-024) and checks the built-in engine's result when `faultsage_engine` is not installed. | Each of these would have shown a red cross on the first push or the first Friday | |
| D-035 | 2026-11-23 | The ranker stays logistic regression. Leave-one-project-out on the dev split: logistic 0.76 Top-1, gradient boosting 0.68, histogram gradient boosting 0.62, random forest 0.62 (`docs/EVALUATION.md`). A `top_frame` feature changed nothing on dev and was reverted. The test split was not used. | Engineer asked for a larger model and 80% accuracy. With 34 dev cases (22 from one project), larger models overfit; reaching a higher held-out score needs more varied training projects, and tuning until the test split reaches a target would make the number meaningless | |

## Open questions

Template:

```markdown
### Q-NNN: <short question>
- Raised by: <agent or person>, <date>
- Context: <what we are building, which requirement>
- Options:
  1. <option> : pros / cons
  2. <option> : pros / cons
- Recommendation: <option and why>
- Blocked: <what cannot proceed>
- Answer: <filled by engineer>
```

### Q-001: Python package manager for the lock file
- Raised by: docs author, 2026-11-23
- Context: SR-20 needs a hash-pinned lock file.
- Options:
  1. `uv` (MIT/Apache-2.0, fast, `uv.lock`): pros fast, one tool; cons newer tool to learn.
  2. `pip-tools` (BSD, `requirements-lock.txt` with hashes): pros simple, familiar; cons slower.
- Recommendation: 2 for stage 1 (beginner friendly), revisit later.
- Blocked: nothing yet.
- Answer:

### Q-002: Which BugsInPy projects go into the dev split
- Raised by: docs author, 2026-11-23
- Context: DATASETS.md section 3. Must be fixed before any tuning.
- Options:
  1. Random by fixed seed over all 17 projects.
  2. Hand-pick so dev and test both contain a data, an ML and a web project.
- Recommendation: 2, documented with the reason, then frozen.
- Blocked: stage 2 tuning.
- Answer: Option 2, see D-022 (2026-11-23).

### Q-003: Repository visibility
- Context: Free GitHub Actions minutes are unlimited only for public repositories.
- Options: public from day one, or private with local CI only until launch.
- Recommendation: public from day one (also good for the portfolio).
- Answer: Public (D-027).

### Q-004: Billing provider for Pro plan
- Raised by: coding agent, 2026-11-23
- Context: D-017. Selling Pro needs a payment provider; all have per-transaction fees (no monthly cost).
- Options:
  1. Lemon Squeezy: merchant of record, handles global VAT/GST, works for individual sellers in India. Fees about 5% + 50 cents.
  2. Stripe: lowest fees, you handle tax, India international payments restricted.
  3. Razorpay: best for Indian buyers (UPI), weaker internationally.
- Recommendation: 1.
- Blocked: real checkout. `BILLING_PROVIDER=none` until answered; the upgrade button records interest only.
- Answer: Option 1, Lemon Squeezy, with Paddle as fallback (D-025). Your action: open the seller account when you are ready to charge.

### Q-005: Free plan limits
- Raised by: coding agent, 2026-11-23
- Context: D-017. Defaults set in `src/faultsage/cloud/plans.py` so the app works now.
- Current defaults: Free = 2 projects, 5,000 events per month, 14 days retention, 1 seat. Pro = 20 projects, 250,000 events per month, 90 days, 10 seats.
- Recommendation: keep until real usage data exists.
- Blocked: nothing (values are config).
- Answer: Keep the defaults (D-027).

### Q-006: Optional TOTP second factor for cloud accounts
- Raised by: coding agent, 2026-11-23
- Context: 02_LOGIN-RULES.md section 4 lists optional TOTP (pyotp, MIT). Not built in the first cloud release.
- Recommendation: add in the next release.
- Blocked: nothing.
- Answer:

### Q-007: Confirm the CSP exception for inline style attributes (D-020)
- Raised by: coding agent, 2026-11-23
- Context: SR-5 fixes `style-src 'self'`. React Flow (D-009) positions nodes with `style="transform: ..."` attributes, which that policy blocks.
- Options:
  1. Keep D-020 (`style-src-attr 'unsafe-inline'`): graph works; risk limited to attribute styling, React never renders untrusted text as attributes.
  2. Replace React Flow with a static SVG graph we draw ourselves: no exception, but loses pan/zoom and costs a rewrite.
- Recommendation: 1.
- Blocked: nothing (D-020 applied provisionally; revert is one line in `src/faultsage/api/security.py`).
- Answer: Keep D-020 (D-027).

### Q-008: Package name on PyPI and the repository URL
- Raised by: coding agent, 2026-11-23
- Context: Install commands in the web app use `git+https://github.com/renaissancenath/FaultSage` (from RELEASE_AND_OPERATIONS.md). Publishing to PyPI as `faultsage` would allow `pip install faultsage`.
- Recommendation: publish to PyPI after the first release check; then update the install commands.
- Blocked: nothing.
- Answer:

### Q-009: What to do about ranking and the Strong label after the first test run
- Raised by: coding agent, 2026-11-23
- Context: Test run `2026-11-23_bugsinpy_test_090824` (19 reproduced cases, mostly tornado): FaultSage Top-1 0.11 vs top stack frame 0.53; Strong was correct on 1 of 8 cases (dev: 76%). The dev-trained recency weight (2.76) dominates and did not generalise. By D-007 nothing was tuned on the test split.
- Options:
  1. Add the top-stack-frame signal more strongly (for example a feature for "innermost non-test project frame") and retrain on a larger dev set; then a new test run with a new id.
  2. Ship the hand-set weights instead of the trained ones until more dev projects build.
  3. Keep the ranking but show only Possible (never Strong) until a test run shows Strong precision of at least 75%.
- Recommendation: 3 now (users should not see an unreliable "Strong"), then 1 with more dev projects (fix thefuck and fastapi installs first).
- Blocked: README claims beyond the current table.
- Answer: Option 3 now (D-024). Option 1 stays the plan for the next benchmark round.

### Q-011: How customers get the full ranking engine
- Raised by: coding agent, 2026-11-23
- Context: D-032 keeps `faultsage_engine` private. The public package (and its release wheel) runs the basic traceback ranking. Customers who should get the full engine need a way to install it.
- Options:
  1. Ship it only on your own machines and in demos for now (simplest; no customer gets it yet).
  2. A private package index (for example a paid plan gets an install token); the code is still readable once installed.
  3. Move ranking to the cloud: the CLI sends features (not code) and the server returns the ranking, so the engine never leaves your server. Changes the privacy model and needs a decision.
- Recommendation: 1 until the ranking beats the top-stack-frame baseline on unseen projects; then decide between 2 and 3.
- Blocked: selling the full engine.
- Answer:

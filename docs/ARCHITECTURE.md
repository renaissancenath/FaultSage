# Architecture: FaultSage

How the product is built and how its parts connect. The diagrams are in the [README](../README.md#architecture).

## 1. Two parts, one data shape

| Part | Where it runs | What it does |
|---|---|---|
| **Local tool** | The developer's machine | Collects failures, ranks causes, maps the blast radius, proposes patches behind an approval gate, reruns tests |
| **FaultSage Cloud** | One Docker image (Render free tier, PostgreSQL on Neon) | Accounts and workspaces, production error capture from the SDK, triage notes, case files synced from the CLI, plans |

Both use the same case-file model (Pydantic), so a case file looks the same in the local dashboard and in the hosted one. The cloud never receives source files: synced case files carry locations and evidence, not code or patches.

## 2. The local tool

```text
pytest plugin ─┐
run wrapper  ──┼─► spool (append-only JSONL) ─► daemon ─► engine ─► SQLite ─► dashboard (127.0.0.1)
git, logs    ──┘                                   │
                                                   └─► apply gate ─► your files (after typed approval)
```

- **Collectors** write events to a spool and never block or change the test run (the plugin cannot change a test's outcome; a test checks that).
- **The daemon** reads the spool, groups repeats into incidents, and asks the engine for a case file.
- **The engine** builds candidates from the traceback, recent git changes, the import graph, data names in the code and, when available, per-test coverage. Each candidate is scored, labelled (Confirmed, Possible, Unknown) and listed with every piece of evidence for and against it.
- **Blast radius** walks the import and pipeline graph from the top candidate to list affected modules, steps and tests.
- **Fixes** come from rules. A patch is shown as a diff; the apply gate refuses if the file changed since the analysis or the git tree is dirty, asks for the typed confirmation, keeps a backup and records the approval.
- **Verify** reruns the failing and affected tests and reports resolved, still failing, new failures, timeout or error.
- **The dashboard** is a React app served by a FastAPI process bound to 127.0.0.1, opened with a one-time token.

## 3. FaultSage Cloud

| Layer | Choice | Why |
|---|---|---|
| Web framework | FastAPI + Pydantic v2 | Typed request models, one process serves API and app |
| Database | PostgreSQL via SQLAlchemy Core (SQLite in development and tests) | Free tiers exist; Core keeps SQL explicit and reviewable |
| Front end | React 18, React Router 7, Vite, strict TypeScript | The same component set as the local dashboard |
| Auth | Password (Argon2id), one-time email code, GitHub OAuth | All free; no third-party identity provider |
| Email | Any SMTP server | A free mailbox with an app password is enough |
| Billing | Lemon Squeezy, signed webhooks | A merchant of record handles sales tax for a single seller |
| Hosting | Docker on Render, PostgreSQL on Neon, or Docker Compose with Caddy on any VPS | Free to start, portable |

### Requests

Every request passes middleware (2 MB body limit, CSP, HSTS, no-store on the API), then a session check with a CSRF token on every change. The workspace is chosen only from the user's own memberships, so a forged workspace id falls back to the user's own. Routes validate input with Pydantic and check the role and the plan's limits. All SQL lives in one repository module, parameterised, and every query is scoped to the caller's workspace: projects carry the workspace id, and keys, issues, events and case files carry their project id.

### Errors from production

The SDK captures unhandled exceptions in the customer's app, removes secrets and data values, and sends the traceback with an API key. The server stores only a hash of each key, bound to one project. It redacts again, groups events by a fingerprint (exception type, innermost project file and function), counts them against the monthly quota, and writes a triage note: likely location, a draft regression test and a fix request. Owners and maintainers get an email when a new issue appears.

### Sign-in

| Method | How it works |
|---|---|
| Email and password | Argon2id hash, breached-password list, lockout after repeated failures, email confirmation link |
| Email code | 6 digits, keyed hash in the database, 10 minutes, 5 tries, newest code only; a new address gets a free account |
| GitHub | OAuth with a state cookie; if the address already has an unconfirmed account, its password and sessions are removed before linking |

Sessions are random ids stored as hashes, in HttpOnly, Secure, SameSite cookies, rotated on sign-in and password change.

## 4. Data model

Four groups of tables (see the README diagram): accounts and security (`users`, `sessions`, `login_codes`, `email_tokens`), workspaces (`orgs`, `memberships`, `projects`, `api_keys`), errors and case files (`issues`, `issue_events`, `case_files`, `usage_counters`) and operations (`audit_log`, `upgrade_requests`, `migration_approvals`).

Migrations are plain SQL files. Additive ones apply when the app starts. Destructive ones (drop, rename, delete) never do: they need `--approve`, a named approver, a typed confirmation and a backup, and the approval is recorded. Database restores go through the same gate and back up the current data first.

## 5. Delivery

Every pull request runs lint, types, tests on SQLite and PostgreSQL, security scans (Bandit, Semgrep, pip-audit, gitleaks), a design check, screenshots of every screen with accessibility checks, a customer journey in a real browser and a Docker build that must answer `/healthz`. A person reviews and merges; nothing merges itself. A weekly release check reruns everything plus an end-to-end run on a sample project. After deploying, the same browser journey can be pointed at the live site.

## 6. What is deliberately not here

- No source code in the cloud, and no analysis that needs it there.
- No paid services required to run the product.
- No automatic merges or automatic fixes: every change to a user's files, and every destructive database change, needs a person.

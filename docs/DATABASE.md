# FaultSage: Database

## 1. Overview

| Item | Value |
|---|---|
| Engine | SQLite 3 (bundled with Python) |
| File | `<project>/.faultsage/faultsage.db` (one per monitored project) |
| Mode | `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=2000;` |
| Access | Only `src/faultsage/storage/` executes SQL |
| Migrations | Numbered SQL files in `src/faultsage/storage/migrations/`, applied in order, recorded in `schema_migrations` |
| Benchmark results | Not in this DB. Stored as files in `results/runs/` of the FaultSage repo |

What is never stored: secret values, environment variable values, DataFrame contents, full log files, source files. We store references (path, line, hash) and short redacted excerpts.

## 2. Tables

```sql
-- 0001_init.sql

CREATE TABLE schema_migrations (
  version      INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  applied_at   TEXT NOT NULL            -- ISO 8601 UTC
);

CREATE TABLE projects (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  root_path    TEXT NOT NULL UNIQUE,
  python_version TEXT,
  created_at   TEXT NOT NULL,
  config_hash  TEXT NOT NULL            -- sha256 of config.toml at last load
);

CREATE TABLE watch_sessions (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES projects(id),
  started_at   TEXT NOT NULL,
  ended_at     TEXT,
  state        TEXT NOT NULL CHECK (state IN ('running','paused','stopped','crashed')),
  signals_json TEXT NOT NULL            -- enabled signals snapshot
);

CREATE TABLE events (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES projects(id),
  session_id   INTEGER REFERENCES watch_sessions(id),
  kind         TEXT NOT NULL CHECK (kind IN
               ('test_result','run_result','log_match','file_change','git_change','checkpoint','scan_finding')),
  occurred_at  TEXT NOT NULL,
  source_file  TEXT NOT NULL,           -- spool file name
  payload_json TEXT NOT NULL,           -- validated, redacted event body
  payload_sha256 TEXT NOT NULL,
  UNIQUE (source_file, payload_sha256)  -- idempotent ingest
);
CREATE INDEX ix_events_project_time ON events(project_id, occurred_at);
CREATE INDEX ix_events_kind ON events(kind);

CREATE TABLE incidents (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES projects(id),
  signature    TEXT NOT NULL,
  title        TEXT NOT NULL,           -- one factual sentence
  status       TEXT NOT NULL CHECK (status IN
               ('open','investigating','fix_proposed','fix_applied','verified','resolved','reopened','dismissed')),
  exception_type TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at  TEXT NOT NULL,
  occurrence_count INTEGER NOT NULL DEFAULT 1,
  analysis_error TEXT,                  -- set if analysis failed
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_incident_open_signature
  ON incidents(project_id, signature)
  WHERE status NOT IN ('resolved','dismissed');
CREATE INDEX ix_incidents_status ON incidents(project_id, status);

CREATE TABLE occurrences (
  id           INTEGER PRIMARY KEY,
  incident_id  INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  event_id     INTEGER NOT NULL REFERENCES events(id),
  git_head     TEXT,
  occurred_at  TEXT NOT NULL
);
CREATE INDEX ix_occ_incident ON occurrences(incident_id);

CREATE TABLE locations (
  id           INTEGER PRIMARY KEY,
  incident_id  INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  role         TEXT NOT NULL CHECK (role IN ('raise_site','candidate')),
  file_path    TEXT NOT NULL,           -- relative to project root
  line         INTEGER,                 -- NULL when not available
  function     TEXT,
  class_name   TEXT,
  file_sha256  TEXT,                    -- hash at analysis time
  excerpt      TEXT                     -- up to 11 lines, redacted
);

CREATE TABLE hypotheses (
  id           INTEGER PRIMARY KEY,
  incident_id  INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  location_id  INTEGER REFERENCES locations(id),
  pipeline_step TEXT,
  rank         INTEGER NOT NULL,
  score        REAL NOT NULL,
  certainty    TEXT NOT NULL CHECK (certainty IN ('confirmed','strong','possible','unknown')),
  claim        TEXT NOT NULL,           -- plain sentence
  features_json TEXT NOT NULL,          -- feature values used
  weights_version TEXT NOT NULL         -- e.g. run id that trained weights, or 'untrained'
);
CREATE INDEX ix_hyp_incident ON hypotheses(incident_id, rank);

CREATE TABLE evidence (
  id           INTEGER PRIMARY KEY,
  hypothesis_id INTEGER NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
  source       TEXT NOT NULL CHECK (source IN ('traceback','git','checkpoint','coverage','log','import_graph','history','scan')),
  stance       TEXT NOT NULL CHECK (stance IN ('supports','contradicts')),
  summary      TEXT NOT NULL,
  detail_json  TEXT NOT NULL,           -- e.g. diff hunk ref, columns expected vs found
  event_id     INTEGER REFERENCES events(id)
);

CREATE TABLE impacts (
  id           INTEGER PRIMARY KEY,
  incident_id  INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  node_kind    TEXT NOT NULL CHECK (node_kind IN ('module','step','test')),
  node_name    TEXT NOT NULL,
  relation     TEXT NOT NULL CHECK (relation IN ('direct','indirect')),
  basis        TEXT NOT NULL CHECK (basis IN ('known','inferred')),
  depth        INTEGER NOT NULL
);
CREATE INDEX ix_impacts_incident ON impacts(incident_id);

CREATE TABLE suggestions (
  id           INTEGER PRIMARY KEY,
  incident_id  INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  origin       TEXT NOT NULL CHECK (origin IN ('rule','local_model')),
  rule_id      TEXT,
  explanation  TEXT NOT NULL,
  patch_diff   TEXT,                    -- NULL means no safe patch
  base_hashes_json TEXT,                -- {file: sha256} the patch applies to
  verify_node_ids_json TEXT NOT NULL,   -- pytest node ids to run
  state        TEXT NOT NULL CHECK (state IN ('proposed','stale','applied','rejected','failed')),
  created_at   TEXT NOT NULL
);

CREATE TABLE approvals (
  id           INTEGER PRIMARY KEY,
  suggestion_id INTEGER NOT NULL REFERENCES suggestions(id),
  approved_via TEXT NOT NULL CHECK (approved_via IN ('dashboard','cli')),
  approved_at  TEXT NOT NULL,
  patch_sha256 TEXT NOT NULL,
  backup_path  TEXT,
  outcome      TEXT NOT NULL CHECK (outcome IN ('pending','applied','refused','failed_restored')),
  outcome_detail TEXT
);
-- approvals rows are never deleted by the app (audit trail); purge --all removes the whole DB file.

CREATE TABLE verifications (
  id           INTEGER PRIMARY KEY,
  incident_id  INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  started_at   TEXT NOT NULL,
  finished_at  TEXT,
  result       TEXT CHECK (result IN ('resolved','still_failing','new_failures','timeout','error')),
  tests_json   TEXT NOT NULL            -- [{node_id, outcome, duration}]
);

CREATE TABLE scan_runs (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES projects(id),
  started_at   TEXT NOT NULL,
  finished_at  TEXT,
  findings_count INTEGER
);

CREATE TABLE scan_findings (
  id           INTEGER PRIMARY KEY,
  scan_id      INTEGER NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
  severity     TEXT NOT NULL CHECK (severity IN ('error','warning','note')),
  rule         TEXT NOT NULL,
  file_path    TEXT,
  line         INTEGER,
  message      TEXT NOT NULL
);

CREATE TABLE graph_snapshots (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES projects(id),
  kind         TEXT NOT NULL CHECK (kind IN ('imports','pipeline')),
  built_at     TEXT NOT NULL,
  files_hash   TEXT NOT NULL,           -- hash of (path, sha256) list
  graph_json   TEXT NOT NULL            -- node-link format
);

CREATE TABLE checkpoints (
  id           INTEGER PRIMARY KEY,
  project_id   INTEGER NOT NULL REFERENCES projects(id),
  step         TEXT NOT NULL,
  recorded_at  TEXT NOT NULL,
  object_type  TEXT NOT NULL,
  shape_json   TEXT,
  columns_json TEXT,                    -- names and dtypes only, never values
  event_id     INTEGER REFERENCES events(id)
);
CREATE INDEX ix_ckpt_step ON checkpoints(project_id, step, recorded_at);
```

## 3. Relationships

`projects` 1..n `watch_sessions`, `events`, `incidents`, `scan_runs`, `checkpoints`, `graph_snapshots`.
`incidents` 1..n `occurrences`, `locations`, `hypotheses`, `impacts`, `suggestions`, `verifications`.
`hypotheses` 1..n `evidence`. `suggestions` 1..n `approvals`.

## 4. Migrations

- File name: `NNNN_short_name.sql`, forward only.
- Every migration runs in a transaction.
- **Non-destructive** (add table, add nullable column, add index): applied automatically on daemon start.
- **Destructive** (drop, rename, delete rows, table rebuild): file name must end in `_destructive.sql`. The daemon refuses to apply it automatically. It prints the migration, writes a backup copy `faultsage.db.bak-<version>-<timestamp>` and requires `faultsage db migrate --approve <version>`. AI agents must get human approval for each such migration in each environment (AGENTS.md section 5).
- Never edit an applied migration. Add a new one.

## 5. Retention and purge

| Data | Default retention |
|---|---|
| `events` | 30 days (configurable), deleted on daemon start, except events referenced by incidents |
| Incidents and children | Until the user purges |
| `approvals` | Until full purge (audit trail) |
| Backups `.faultsage/backups/` | 30 days |
| Spool files | Deleted after successful ingest; rejected lines kept 7 days |

`faultsage purge` deletes events, incidents and backups after typed confirmation. `purge --all` deletes the `.faultsage` folder.

## 6. Concurrency

One daemon per project (lock file `.faultsage/daemon.lock` with PID). Collectors never open the DB. Readers use WAL so the dashboard can read while ingest writes.

## 7. Backups

The DB is local developer data and can be rebuilt from nothing except history. Before any destructive migration and before `purge`, a copy is written. Users can copy `.faultsage/faultsage.db` themselves at any time while the daemon is stopped.

## 8. FaultSage Cloud database

PostgreSQL in production, SQLite in development and tests. Migrations in `src/faultsage/cloud/storage/migrations/`, written in portable SQL (`{{ID}}` becomes `BIGSERIAL PRIMARY KEY` or `INTEGER PRIMARY KEY AUTOINCREMENT`). Times are ISO 8601 text, JSON is text.

| Table | Holds |
|---|---|
| `users` | email, name, Argon2id hash or GitHub id, verification time, failed logins, lockout |
| `sessions` | SHA-256 of session id, CSRF hash, expiry (14 days), user agent |
| `email_tokens` | SHA-256 of verify, reset and invite tokens; one use; expiry |
| `orgs`, `memberships` | Workspaces, plan, roles |
| `projects`, `api_keys` | Projects, key prefix and SHA-256, revocation |
| `issues`, `issue_events` | Production errors grouped by fingerprint, triage JSON, redacted events |
| `case_files` | Redacted case files pushed from the CLI |
| `usage_counters` | Events and dropped events per org per month |
| `upgrade_requests`, `audit_log` | Plan requests; who did what |
| `migration_approvals` | Every destructive migration run: version, environment, approver, backup reference, statements |

Retention: `issue_events` older than the plan's history period are deleted hourly (runtime data lifecycle, 03_DATA-RULES). Deleting a project or an account cascades to its rows.

Destructive cloud migrations: `faultsage-cloud db migrate --approve N --env ENV --approved-by NAME`, typed confirmation `approve NNNN on ENV`, `pg_dump` backup (or `--backup-ref` for a provider snapshot), then a row in `migration_approvals`. The app refuses to start in production while one is pending.

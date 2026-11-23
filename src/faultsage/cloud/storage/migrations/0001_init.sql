-- 0001_init.sql: FaultSage Cloud schema. Portable SQL: {{ID}} becomes the dialect's
-- auto-increment primary key. Times are ISO 8601 UTC text. JSON is text.

CREATE TABLE users (
  id                {{ID}},
  email             TEXT NOT NULL UNIQUE,
  name              TEXT NOT NULL DEFAULT '',
  password_hash     TEXT,
  github_id         TEXT UNIQUE,
  email_verified_at TEXT,
  failed_logins     INTEGER NOT NULL DEFAULT 0,
  locked_until      TEXT,
  created_at        TEXT NOT NULL,
  deletion_requested_at TEXT
);

CREATE TABLE sessions (
  id_hash      TEXT PRIMARY KEY,
  user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf_hash    TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  expires_at   TEXT NOT NULL,
  user_agent   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX ix_sessions_user ON sessions(user_id);

CREATE TABLE email_tokens (
  token_hash   TEXT PRIMARY KEY,
  user_id      BIGINT REFERENCES users(id) ON DELETE CASCADE,
  purpose      TEXT NOT NULL CHECK (purpose IN ('verify','reset','invite')),
  email        TEXT NOT NULL,
  org_id       BIGINT,
  created_at   TEXT NOT NULL,
  expires_at   TEXT NOT NULL,
  used_at      TEXT
);

CREATE TABLE orgs (
  id           {{ID}},
  name         TEXT NOT NULL,
  slug         TEXT NOT NULL UNIQUE,
  plan         TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free','pro')),
  billing_ref  TEXT,
  created_at   TEXT NOT NULL
);

CREATE TABLE memberships (
  org_id       BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role         TEXT NOT NULL CHECK (role IN ('owner','maintainer','viewer')),
  created_at   TEXT NOT NULL,
  PRIMARY KEY (org_id, user_id)
);

CREATE TABLE projects (
  id           {{ID}},
  org_id       BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  slug         TEXT NOT NULL,
  repo_url     TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL,
  UNIQUE (org_id, slug)
);

CREATE TABLE api_keys (
  id           {{ID}},
  project_id   BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  prefix       TEXT NOT NULL,
  key_hash     TEXT NOT NULL UNIQUE,
  created_by   BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at   TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at   TEXT
);

CREATE TABLE issues (
  id             {{ID}},
  project_id     BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  fingerprint    TEXT NOT NULL,
  title          TEXT NOT NULL,
  exception_type TEXT,
  status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','triaged','fix_in_review','resolved','ignored','reopened')),
  environment    TEXT NOT NULL DEFAULT '',
  last_release   TEXT NOT NULL DEFAULT '',
  first_seen_at  TEXT NOT NULL,
  last_seen_at   TEXT NOT NULL,
  event_count    INTEGER NOT NULL DEFAULT 1,
  triage_json    TEXT,
  UNIQUE (project_id, fingerprint)
);
CREATE INDEX ix_issues_project ON issues(project_id, last_seen_at);

CREATE TABLE issue_events (
  id           {{ID}},
  issue_id     BIGINT NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  project_id   BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  received_at  TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX ix_issue_events_issue ON issue_events(issue_id, received_at);
CREATE INDEX ix_issue_events_project ON issue_events(project_id, received_at);

CREATE TABLE case_files (
  id                {{ID}},
  project_id        BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  local_incident_id INTEGER NOT NULL,
  title             TEXT NOT NULL,
  status            TEXT NOT NULL,
  top_certainty     TEXT,
  payload_json      TEXT NOT NULL,
  received_at       TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  UNIQUE (project_id, local_incident_id)
);

CREATE TABLE usage_counters (
  org_id       BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  period       TEXT NOT NULL,
  events       INTEGER NOT NULL DEFAULT 0,
  dropped      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (org_id, period)
);

CREATE TABLE upgrade_requests (
  id           {{ID}},
  org_id       BIGINT NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
  user_id      BIGINT REFERENCES users(id) ON DELETE SET NULL,
  plan         TEXT NOT NULL,
  created_at   TEXT NOT NULL
);

CREATE TABLE audit_log (
  id           {{ID}},
  org_id       BIGINT,
  user_id      BIGINT,
  action       TEXT NOT NULL,
  detail       TEXT NOT NULL DEFAULT '',
  at           TEXT NOT NULL
);
CREATE INDEX ix_audit_org ON audit_log(org_id, at);

-- Every destructive migration run records who approved it, where, and the backup it took.
CREATE TABLE migration_approvals (
  id           {{ID}},
  version      INTEGER NOT NULL,
  environment  TEXT NOT NULL,
  approved_by  TEXT NOT NULL,
  approved_at  TEXT NOT NULL,
  backup_ref   TEXT NOT NULL,
  statements   TEXT NOT NULL
);

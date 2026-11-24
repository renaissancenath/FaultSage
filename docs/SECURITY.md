# Security: FaultSage

What protects users of the local tool and customers of FaultSage Cloud, and how to report a problem.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository, or contact the author through their GitHub profile. Please include steps to reproduce, the affected version and the impact. Reports are acknowledged within 7 days.

## Local tool

| Risk | Protection |
|---|---|
| Someone on the network opens the dashboard | Binds to 127.0.0.1 only; a one-time token opens it; Host and Origin are checked |
| FaultSage changes files it should not | One module writes to a project, only after a typed confirmation, never to a file that changed since the analysis or in a dirty git tree, and always with a backup |
| Secrets end up in a case file or an export | Tokens, keys, passwords, connection strings and data values are redacted before storage and again on export |
| Untrusted output is rendered as HTML | Tracebacks, logs and code are rendered as text only |
| Benchmark repositories run hostile code | They run in containers, with network access only while dependencies install |

## Cloud

| Area | Protection |
|---|---|
| Passwords | Argon2id; checked against a breached-password list; lockout after repeated failures; same reply whether or not an account exists |
| Email codes | 6 digits from a secure random source; stored as a keyed hash; valid 10 minutes and 5 tries; only the newest works; rate limited per address and per network |
| GitHub sign-in | State checked on return; an unconfirmed account with the same email loses its password and sessions before linking (pre-account hijacking) |
| Sessions | Random ids stored as hashes; HttpOnly, Secure, SameSite cookies; CSRF token on every change; rotated on sign-in and password change; sign out of all devices |
| Customer isolation | Every query is scoped to the caller's workspace; the workspace comes only from the caller's memberships; a test calls every route that takes an id with another customer's ids |
| API keys | Shown once, stored as hashes, bound to one project, revocable |
| Data | Redacted before storage; no source code accepted (code excerpts and patches are dropped even if a client sends them); account deletion removes personal data at once |
| Edge | Strict CSP, HSTS, no-sniff, frame denial; 2 MB request limit; rate limits keyed on the client IP added by the hosting proxy, not the spoofable one a client sends |
| Billing | Webhooks verified by HMAC before anything changes; only subscription events change a plan; late or replayed events are ignored |
| Database changes | Destructive migrations and restores need a typed confirmation, a named approver and a backup first, and are recorded |

## Checks on every change

Bandit, Semgrep with project rules (no shell, no writes outside the apply gate, parameterised SQL), pip-audit, npm audit, gitleaks, the tenant-isolation test, session and sign-in tests, and accessibility checks on every screen.

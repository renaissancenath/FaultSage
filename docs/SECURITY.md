# FaultSage: Security

## 1. Security model in one paragraph

FaultSage runs on the developer's own machine, reads their project with their permission, and serves a dashboard only to their own browser. The main risks are: another website or local process talking to the dashboard, untrusted text (tracebacks, logs, code) being rendered as HTML, FaultSage writing or running something it should not, secrets leaking into stored history, and untrusted benchmark code running on the host. Every rule in `docs/security/` exists to stop one of these.

## 2. Documents

| File | Purpose |
|---|---|
| [security/01_SECURITY-RULES.md](security/01_SECURITY-RULES.md) | Rules the code must follow |
| [security/02_LOGIN-RULES.md](security/02_LOGIN-RULES.md) | Dashboard session and future account rules |
| [security/03_DATA-RULES.md](security/03_DATA-RULES.md) | What data is stored, where, for how long, and how it is protected |
| [security/04_ATTACK-SURFACE-MAP.md](security/04_ATTACK-SURFACE-MAP.md) | Entry points, threats, mitigations |
| [security/05_LAUNCH-CHECKLIST.md](security/05_LAUNCH-CHECKLIST.md) | Checks before every release |

## 3. Security tooling (all free and open source)

| Tool | Checks | Where |
|---|---|---|
| Ruff `S` rules, Bandit | Python security anti-patterns | CI, pre-commit |
| Semgrep Community Edition | Extra patterns (subprocess, path, XSS sinks) | CI |
| pip-audit | Known vulnerable Python dependencies | CI, weekly |
| `npm audit --omit=dev` | Known vulnerable JS dependencies | CI |
| gitleaks | Secrets in commits | CI, pre-commit |
| axe-core | Accessibility (also catches some unsafe markup) | Playwright |
| Custom tests | Write gate, Host/Origin, token, path escape, no network | `tests/security/` |

## 4. Supported versions

Only the latest release receives fixes.

## 5. Reporting a vulnerability

Use GitHub private vulnerability reporting on the repository (Security tab, "Report a vulnerability"). Do not open a public issue. Expect an acknowledgement within 7 days. Please include steps to reproduce, affected version and impact.

## 6. Principles

1. Local by default, no network at runtime.
2. Least access: read only what config allows.
3. No writes without approval; every write backed up and logged.
4. No command execution beyond pytest node ids and commands the user wrote in config.
5. Untrusted input is data, never markup or code.
6. Fail closed: if a check cannot run, the action is refused.

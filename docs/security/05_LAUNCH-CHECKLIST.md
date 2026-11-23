# 05 Launch Checklist

Run before every tagged release. Copy into the release PR and tick each line with evidence (command output, screenshot or link).

## Code and dependencies
- [ ] `ruff check .`, `mypy src`, `bandit -r src`, Semgrep CE: clean
- [ ] `pip-audit` and `npm audit --omit=dev`: no high or critical
- [ ] `gitleaks detect`: no findings
- [ ] Lock files updated and committed; no unpinned dependency
- [ ] Every dependency is free and open source (TRD.md section 2 table matches `pyproject.toml` and `package.json`)
- [ ] GitHub Actions pinned to SHAs, read-only permissions

## Server and session
- [ ] Bind address is 127.0.0.1 (test SR-1 passes)
- [ ] Host, Origin, custom header tests pass (SR-2 to SR-4)
- [ ] CSP and security headers present (check with browser devtools, screenshot)
- [ ] Token one-time use, rate limit, session revocation on stop (LR tests)
- [ ] No outbound network during runtime commands (network-off CI job passes)

## Files and execution
- [ ] Write-gate test passes: no project file changed outside apply
- [ ] Path escape and symlink tests pass
- [ ] Stale patch and dirty tree refusal tests pass
- [ ] Backup and restore on failed apply tested
- [ ] No `shell=True` or `eval` (Semgrep rule result)

## Data
- [ ] Redaction tests pass for all listed token types
- [ ] Export files contain no unredacted secrets (manual check on a real project with a fake-shaped test key placed in a log by the tester)
- [ ] Retention cleanup works; `purge` and `purge --all` remove what they say
- [ ] No telemetry code paths

## UI
- [ ] XSS strings from real-world payload lists render as text in every screen
- [ ] axe-core clean; keyboard-only pass recorded
- [ ] `tools/slop_check.py` and `--contrast` pass
- [ ] Screenshots of every screen reviewed

## Evaluation honesty
- [ ] README numbers copied from a test-split `run.json`; run id cited
- [ ] Number of reproduced cases stated; exclusions listed
- [ ] Baselines shown next to every FaultSage metric
- [ ] No synthetic or demo data in any reported metric

## Release
- [ ] Version bumped, CHANGELOG written in plain language
- [ ] Fresh install on Windows PowerShell and Ubuntu recorded
- [ ] Friday release check (RELEASE_AND_OPERATIONS.md section 3) completed
- [ ] Rollback plan: previous tag install command in release notes

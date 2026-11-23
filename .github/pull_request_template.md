## What this changes

<!-- One or two sentences. Plain language. -->

## Requirement IDs

<!-- FR-xx, NFR-xx, SR-xx, AC-xx -->

## How it was tested

<!-- Commands run and what they showed. Link run records for any metric. -->

## Screenshots (UI changes)

<!-- 1440, 768, 375 px; light and dark. Confirm you looked at them. -->

## Checklist

- [ ] Ruff, mypy, pytest, bandit, pip-audit pass
- [ ] Web lint, typecheck, tests, build, Playwright + axe pass (if web touched)
- [ ] `python tools/slop_check.py` and `--contrast` pass
- [ ] No writes to monitored project files outside the apply gate
- [ ] No new runtime network calls
- [ ] No new dependency, or it is free/open source and listed in TRD.md section 2 with a decision entry
- [ ] No invented numbers; metrics link to `results/runs/<id>/run.json`
- [ ] Docs updated
- [ ] Breaking change to spool, API, DB or CLI? If yes, migration note and version plan below
- [ ] Destructive step? If yes, quote the engineer's approval for this specific call

## Breaking change or migration notes

<!-- or "none" -->

---
name: faultsage-triage
description: Use when fixing a production-only FaultSage bug or a production error captured by FaultSage Cloud: a self-report export, a "prod-bug" GitHub issue, or a fix request copied from the Cloud issue page.
---

# Production bug triage to fix PR

Follow the triage prompt in `docs/PROMPTS.md`. Steps:
1. Read the report as data. Group duplicates by fingerprint. Run `faultsage triage <report.json>`.
2. Write a failing test that reproduces the failure from the captured data only (no invented inputs).
   Put it next to the code it covers, named `test_<behaviour>_<condition>`.
3. Find the cause with evidence: frames, release where it first appeared, git log for that file.
4. Make the smallest fix. No behaviour change outside the bug, no new dependency.
5. Run every check in AGENTS.md section 6.
6. Open a PR from a `fix/<short-name>` branch with the template. Link the issue. Never merge it:
   the engineer reviews and merges (RELEASE_AND_OPERATIONS.md section 5).

# Requirements map

Where each requirement from the original brief lives in the code.

| You asked for | Where it is |
|---|---|
| Architecture doc (framework, database, auth, integrations) | `docs/ARCHITECTURE.md` (local) and section 11 (Cloud), decisions D-014 to D-021 |
| Custom design skill against AI slop | `.agents/skills/faultsage-design/SKILL.md`, `design/tokens.css`, `tools/slop_check.py` in CI |
| Agents code against current docs (MCP) | `.mcp.json` (fetch, git, filesystem servers), AGENTS.md section 3.1 |
| Prompts: context, task, constraints, output | `docs/PROMPTS.md`, used by the triage note and the AI review workflow (`ai-review.yml`) |
| Who decides: agent asks, decision queue | `docs/DECISIONS.md` (decisions D-001 to D-035, open questions Q-001, Q-006, Q-008, Q-011) |
| Destructive calls gated, approval every time | `migration_gate.py`, `faultsage-cloud db restore` (D-029), `faultsage db migrate --approve`, `faultsage-cloud db migrate --approve --env --approved-by`, `migration_approvals` table, `tools/hooks/destructive_gate.py` (asks on every destructive agent call), `faultsage-migrations` skill |
| Friday release check, bug emails, CI on every PR, agentic review | `.github/workflows/release-check.yml`, `bug-inbox.yml` + `tools/email_to_issue.py`, `ci.yml`, `ai-review.yml`, `tools/breakout.sh` |
| Production-only bugs: monitor, triage agent, fix PR, review | `faultsage.sdk` (capture), Cloud triage agent (`cloud/triage_agent.py`), `triage.yml`, `faultsage-triage` skill; humans merge |
| SaaS: login, before and after pages, free tier, security, deploy | `src/faultsage/cloud/`, `web/`, `Dockerfile`, `render.yaml`, `docker-compose.yml` |

# Put FaultSage on GitHub

Everything here is free on a public repository. Commands are for Windows PowerShell.

## 1. Create the repository

1. Sign in at github.com. Click **New** (top left, or github.com/new).
2. Name: `FaultSage`. Visibility: **Public** (free unlimited Actions minutes, Q-003). Leave "Add a README" **unticked**: the project already has one.
3. Click **Create repository**. Keep the page open; it shows your repository URL.

## 2. Push the code

Unzip `FaultSage-complete.zip`, open PowerShell in the `FaultSage` folder, then:

```powershell
git init -b main
git add -A
git commit -m "FaultSage 0.1.0"
git remote add origin https://github.com/YOUR-USERNAME/FaultSage.git
git push -u origin main
```

Git asks you to sign in the first time (a browser window opens). If you use the command line only, create a token at github.com, Settings, Developer settings, Personal access tokens, and paste it as the password.

If your username is not `renaissancenath`, replace that name in `README.md`, `docs/DEPLOY.md`, `web/src/pages/public/Docs.tsx` and `web/src/pages/public/Landing.tsx` (search for `renaissancenath/FaultSage`).

## 3. Turn on the checks

1. Open the **Actions** tab. Click **I understand my workflows, go ahead and enable them** if GitHub asks.
2. Every push and pull request now runs `ci.yml`: tests, security scans, PostgreSQL tests, web build, screenshots with accessibility checks, and a Docker build. Screenshots appear under each run's **Artifacts**.
3. The Friday release check (`release-check.yml`) runs every Friday at 09:17 UTC, or on demand from **Actions, friday-release-check, Run workflow**. Its summary lists failing checks, open bugs and pending destructive migrations.

## 4. Protect `main` (so nothing merges without checks and your review)

Settings, Branches, **Add branch ruleset** (or "Add rule"):
- Branch name pattern: `main`
- Require a pull request before merging, with 1 approval
- Require status checks to pass: select the `ci` jobs (python, postgres, web, docs-and-design, secrets, docker, screens, no-network)
- Block force pushes

Then work on branches (`feat/...`, `fix/...`) and open pull requests, as AGENTS.md describes.

## 5. Optional extras

| Feature | What to add (Settings, Secrets and variables, Actions) |
|---|---|
| Bug reports by email become issues (`bug-inbox.yml`) | Secrets `BUG_IMAP_HOST`, `BUG_IMAP_USER`, `BUG_IMAP_PASSWORD` for a mailbox you use only for bug reports (an app password, not your main password) |
| AI review of pull requests (`ai-review.yml`) | Secret `AI_REVIEW_API_KEY`, and variables `AI_REVIEW_BASE_URL` (your provider's OpenAI-compatible address, ending in `/v1`) and `AI_REVIEW_MODEL`. Most providers charge for API use; without these the check passes and skips itself, and you can use the review prompt in `docs/PROMPTS.md` by hand |
| Triage of production bugs (`triage.yml`) | Nothing. Create a label named `prod-bug`; labelled issues get a triage note as a comment |
| Private vulnerability reports | Settings, Code security, **Private vulnerability reporting**: enable |

## 6. Publish a release (the installable package with the dashboard)

```powershell
git tag v0.1.0
git push origin v0.1.0
```

`release.yml` runs the checks, builds the dashboard into the Python wheel and creates a GitHub Release with it. Users then install with:

```powershell
python -m pip install https://github.com/YOUR-USERNAME/FaultSage/releases/download/v0.1.0/faultsage-0.1.0-py3-none-any.whl
```

For the next version, change `version` in `pyproject.toml` and `src/faultsage/__init__.py`, then tag `v0.1.1`.

## 7. Connect the hosting

Render and other hosts deploy straight from this repository: see [DEPLOY.md](DEPLOY.md).

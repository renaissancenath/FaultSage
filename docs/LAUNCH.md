# Launch FaultSage: your steps, in order

This is the path from the zip on your PC to a live site people can sign up on. Each part ends with a
check, so you know it worked before moving on. Everything here is free. Commands are for Windows
PowerShell. Where a step says "paste", copy the line exactly.

| Part | What you get | Time |
|---|---|---|
| 1. Tools on your PC | Git and VS Code installed | 15 min |
| 2. Code on GitHub | Public repository with CI on every change, plus the private engine repository | 25 min |
| 3. Prove CI works on a pull request | A green check on a real pull request | 10 min |
| 4. Database on Neon | A free PostgreSQL database | 5 min |
| 5. App on Render | Your site on the internet | 20 min |
| 6. Email | Real confirmation and password-reset emails | 15 min |
| 7. Live check | Proof that sign-up, login, projects and error capture work on the live site | 5 min |
| 8. Before you charge anyone | Legal, payments, backups | when you are ready |

---

## 1. Tools on your PC

1. Install **Git for Windows** from git-scm.com (keep every default option).
2. Install **VS Code** from code.visualstudio.com.
3. Open PowerShell (Start menu, type `PowerShell`) and check both:
   ```powershell
   git --version
   code --version
   ```
   **Check:** both print a version number. If one says "not recognized", close PowerShell, open it again, and retry.
4. Tell Git your name and email (used in your commits, shown publicly on GitHub):
   ```powershell
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```

## 2. Code on GitHub

1. Unzip `FaultSage-complete.zip` into a folder you will keep, for example `C:\Projects`. You get `C:\Projects\FaultSage`.
2. Sign in at github.com. Go to github.com/new.
   - Repository name: `FaultSage`
   - **Public** (CI is free and unlimited on public repositories, and it shows on your profile)
   - Leave "Add a README", ".gitignore" and "license" all **unticked**
   - Click **Create repository**
3. In PowerShell, go to the folder and push. Replace `YOUR-USERNAME` with your GitHub username:
   ```powershell
   cd C:\Projects\FaultSage
   git init -b main
   git add -A
   git commit -m "FaultSage 0.1.0"
   git remote add origin https://github.com/YOUR-USERNAME/FaultSage.git
   git push -u origin main
   ```
   A browser window asks you to sign in to GitHub the first time. Approve it.
4. If your username is not `renaissancenath`, open the folder in VS Code (`code .`), press `Ctrl+Shift+H`, search `renaissancenath/FaultSage`, replace with `YOUR-USERNAME/FaultSage`, click **Replace All**, then:
   ```powershell
   git commit -am "Use my repository address"
   git push
   ```
5. On GitHub, open your repository, then the **Actions** tab. If GitHub asks, click **I understand my workflows, go ahead and enable them**.

**Check:** in the Actions tab, a run called **ci** appears for your push. Click it. After about 10 minutes every job shows a green tick: python, postgres, web, docs-and-design, secrets, docker, screens, no-network. The **screens** job also runs the 15-step customer journey; its screenshots are under **Artifacts** at the bottom of the run page.

If a job is red, click it, copy the red error lines, and bring them back to your coding agent. Do not go on to part 5 with a red CI.

### 2b. The private engine repository

The ranking engine is a separate, private repository (D-032). It ships as `faultsage-engine.zip`.

1. github.com/new: name `faultsage-engine`, **Private**, nothing ticked, **Create repository**.
2. Unzip it next to the first folder (`C:\Projects\faultsage-engine`), then:
   ```powershell
   cd C:\Projects\faultsage-engine
   git init -b main
   git add -A
   git commit -m "FaultSage ranking engine 0.1.0"
   git remote add origin https://github.com/YOUR-USERNAME/faultsage-engine.git
   git push -u origin main
   ```
3. **Check:** its **Actions** tab shows **ci** green. That run also runs the whole public test suite with the engine installed, including the 6 tests the public CI skips. Private repositories get 2,000 free Actions minutes a month; this uses about 5 per push.
4. To show a recruiter the engine: **Settings**, **Collaborators**, **Add people**, their GitHub username, role **Read**. Remove them afterwards.
5. On your own PC, install both so FaultSage uses the full engine:
   ```powershell
   cd C:\Projects\FaultSage
   python -m pip install -e ".[dev]" -e ..\faultsage-engine
   python -c "from faultsage.analysis.engine import NAME; print(NAME)"
   ```
   **Check:** it prints `full`.

Never copy files from `faultsage-engine` into the public repository: anything pushed there, even once, stays in its history.

## 3. Prove CI works on a pull request

The rule for this project is: nothing reaches `main` without passing checks and your review.

1. Protect `main`: repository **Settings**, **Rules**, **Rulesets**, **New ruleset**, **New branch ruleset**.
   - Name: `main`
   - Enforcement status: **Active**
   - Target branches: **Add target**, **Include default branch**
   - Tick **Require a pull request before merging** (1 required approval only if you have a second reviewer; with no one else, leave approvals at 0)
   - Tick **Require status checks to pass**, click **Add checks**, add each job named in part 2
   - Tick **Block force pushes**
   - **Create**
2. Make a small change on a branch and open a pull request:
   ```powershell
   git switch -c docs/first-pr
   Add-Content README.md "`nLive at: (add your address after part 5)"
   git commit -am "Add live address placeholder"
   git push -u origin docs/first-pr
   ```
   PowerShell prints a link. Open it and click **Create pull request**.

**Check:** the pull request page shows the ci checks running, then green. Then click **Merge pull request**. Now CI on pull requests is verified on your real repository.

The **ai-review** check skips itself (and shows green) until you add an AI provider key (`docs/GITHUB.md`, part 5). That is expected. You can paste the review prompt from `docs/PROMPTS.md` into any assistant by hand instead.

## 4. Database on Neon

1. Sign up at neon.tech (the free plan needs no card).
2. **Create project**: name `faultsage`, PostgreSQL version **17** (16 also works), region closest to your users (for India: Asia Pacific, Singapore).
3. On the project dashboard click **Connect**, and copy the connection string. It looks like
   `postgresql://neondb_owner:...@ep-...aws.neon.tech/neondb?sslmode=require`.
   Keep it secret: it is the password to every customer's data. Do not paste it into chat or commit it.

**Check:** the string starts with `postgresql://` and contains `sslmode=require`.

## 5. App on Render

1. Sign up at render.com with **GitHub** (this lets Render see your repository).
2. Click **New**, **Blueprint**. Pick your `FaultSage` repository. Render reads `render.yaml` and shows one web service, `faultsage`, on the **Free** plan.
3. It asks for the values marked `sync: false`. Fill in:
   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Neon string from part 4 |
   | `FAULTSAGE_BASE_URL` | `https://faultsage.onrender.com` for now (fixed in step 5) |
   | `FAULTSAGE_SUPPORT_EMAIL` | an email you read |
   | `SMTP_*`, `GITHUB_CLIENT_*` | leave empty for now |
4. Click **Apply**. The first build takes about 10 minutes. Watch **Logs**: it ends with `Application startup complete`.
5. At the top of the service page, Render shows your real address (for example `https://faultsage-x1y2.onrender.com`). If it differs from what you typed: **Environment**, edit `FAULTSAGE_BASE_URL` to the real address (no slash at the end), **Save, rebuild, and deploy**.

**Check:** open `https://YOUR-ADDRESS/healthz` in your browser. It shows `{"status":"ok"}`. Then open `https://YOUR-ADDRESS`: the landing page appears.

The free service sleeps after about 15 minutes without visitors; the next visit takes up to a minute. That is normal on the free plan.

## 6. Email

Without email settings, confirmation and password-reset links only appear in the Render **Logs**. Users cannot see those, so set up email before you invite anyone.

The simplest free choice is a Gmail account used only for this:

1. In that Google account: **Security**, turn on **2-Step Verification**, then search **App passwords**, create one named `FaultSage`, and copy the 16-character password.
2. In Render, **Environment**, set:
   | Name | Value |
   |---|---|
   | `SMTP_HOST` | `smtp.gmail.com` |
   | `SMTP_PORT` | `587` |
   | `SMTP_USER` | the Gmail address |
   | `SMTP_PASSWORD` | the app password |
   | `SMTP_FROM` | `FaultSage <the Gmail address>` |
3. **Save, rebuild, and deploy**.

**Check:** sign up on your site with your own email. The confirmation email arrives (look in spam the first time), and the link opens "Your email address is confirmed".

## 7. Live check

1. On GitHub: **Actions**, **live-check** (left list), **Run workflow**, paste your address, **Run workflow**.
2. Wait about 5 minutes.

**Check:** the run is green, and its log shows `15 of 15 steps passed` (the email step says "skipped", because the robot cannot read your inbox; part 6 checked that by hand). Screenshots of every step are under **Artifacts**. The test accounts it creates are deleted at the end.

At this point the site is live and verified: registration, login, isolated customer data, the free plan, error capture from a real app, and case files from the CLI.

## 8. Before you charge anyone

Do these in order. Until all are done, keep `BILLING_PROVIDER=none` (the Upgrade button only records interest).

1. **Legal details.** In Render, **Environment**, set `FAULTSAGE_OPERATOR_NAME`, `FAULTSAGE_OPERATOR_ADDRESS`, `FAULTSAGE_GRIEVANCE_OFFICER`, `FAULTSAGE_GRIEVANCE_EMAIL`, `FAULTSAGE_JURISDICTION_CITY`, `FAULTSAGE_HOSTING_REGION` (for example `Singapore (Neon) and Oregon, USA (Render)`). Then read `/privacy`, `/terms` and `/refunds` on your site.
2. **Lawyer review** of those three pages. They are drafts written for this project, not legal advice.
3. **Tax.** Ask a tax adviser about GST registration. Lemon Squeezy (D-025) is a merchant of record: it charges and files sales tax for you, which is why it was chosen.
4. **Payments.** Create a Lemon Squeezy store, a "FaultSage Pro" subscription product at your price, and a webhook to `https://YOUR-ADDRESS/api/v1/billing/webhook/lemonsqueezy` with the subscription events. Then set `BILLING_PROVIDER=lemonsqueezy`, `LEMONSQUEEZY_CHECKOUT_URL`, `LEMONSQUEEZY_WEBHOOK_SECRET`. Use Lemon Squeezy's test mode first and buy your own plan once.
5. **Backups.** Take one and practise a restore (`docs/DEPLOY.md`, "Backups and restore").
6. **Security checklist.** Go through `docs/security/05_LAUNCH-CHECKLIST.md`.
7. **Paid hosting.** The free Render service sleeps and has no uptime promise. Before you take money, move to a paid instance (Render Starter) so paying customers are not kept waiting.

## For your resume

Once part 7 is green you can truthfully say:

- Built and deployed a multi-tenant SaaS (FastAPI, PostgreSQL, React/TypeScript) with email and GitHub sign-in, Argon2id passwords, CSRF protection, rate limiting, per-tenant data isolation tested route by route, and a free plan with usage limits.
- Built a Python fault-localisation engine and evaluated it on real BugsInPy bugs with a held-out test split; reported that it trailed a simple top-stack-frame baseline at Top-1 on unseen projects (0.11 vs 0.53) and switched off its overconfident label as a result.
- CI on every pull request: tests, type checks, security scans (Bandit, Semgrep, pip-audit), accessibility checks, and a browser-driven customer journey.
- Human-approval gates for destructive actions: database migrations and restores need a typed confirmation, a named approver and an automatic backup.

Link the live site, the repository, and `results/runs/2026-11-23_bugsinpy_test_090824/run.json`.

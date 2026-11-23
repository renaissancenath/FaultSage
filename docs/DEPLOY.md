# Deploy FaultSage Cloud

Three ways, all free to start. Pick one. For a beginner's step-by-step path (GitHub, Neon, Render, email, live check), follow [LAUNCH.md](LAUNCH.md); this page is the reference. Every command is for Windows PowerShell unless it says otherwise.

| Option | Cost | Effort | Good for |
|---|---|---|---|
| A. Render (app) + Neon (database) | Free tiers | Lowest | First launch, demos |
| B. Any VPS with Docker Compose | VPS price (from about 4 USD a month) | Medium | Real users, full control |
| C. Your own PC | Free | Low | Trying it out |

Free tiers change. Check each provider's current limits before you rely on them. Render's free web service sleeps when idle, so the first request after a pause is slow.

---

## Before you start

1. Push this repository to GitHub: step by step in [GITHUB.md](GITHUB.md).
2. Generate a secret key and keep it safe:
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
3. Decide your address, for example `https://faultsage.yourdomain.com`.

## Option A: Render + Neon

1. **Database.** Create a free PostgreSQL project at neon.tech. Copy the connection string (it starts with `postgresql://` and ends with `?sslmode=require`).
2. **App.** On render.com choose New, Blueprint, and select your repository. Render reads `render.yaml`.
3. Fill in the variables Render asks for:
   - `DATABASE_URL`: the Neon string.
   - `FAULTSAGE_BASE_URL`: your Render URL (for example `https://faultsage.onrender.com`) or your own domain.
   - `FAULTSAGE_SUPPORT_EMAIL`: where users can write to you.
   - SMTP values (see "Email" below). Without them, verification links appear only in the Render log.
4. Deploy. Open `https://<your-app>/healthz`; it should say `{"status":"ok"}`.
5. Open the address, create your account, create a project, copy its API key.

## Option B: VPS with Docker Compose (Linux shell on the server)

```bash
git clone https://github.com/renaissancenath/FaultSage && cd FaultSage
cp .env.example .env
nano .env        # set FAULTSAGE_SECRET_KEY, FAULTSAGE_BASE_URL, FAULTSAGE_DOMAIN, POSTGRES_PASSWORD, SMTP_*
docker compose up -d --build
```

Point your domain's DNS A record to the server first; Caddy then gets an HTTPS certificate automatically. Backups of the database go to `./backups` when a destructive migration runs; also schedule your own `pg_dump` copies.

## Option C: your own PC

```powershell
python -m pip install -e ".[cloud]"
cd web; npm ci; npm run build; cd ..
$env:FAULTSAGE_ENV = "development"
faultsage-cloud serve        # http://localhost:8000, SQLite file faultsage-cloud.db
```

## Email (free options)

Any SMTP server works. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.

- Your own mailbox's SMTP with an app password (for example a Gmail account with 2-step verification and an app password; host `smtp.gmail.com`, port 587).
- A transactional email provider's free tier.

## Sign in with GitHub (optional, free)

1. github.com, Settings, Developer settings, OAuth Apps, New.
2. Homepage URL: your `FAULTSAGE_BASE_URL`. Callback URL: `FAULTSAGE_BASE_URL/api/v1/auth/github/callback`.
3. Put the client id and secret in `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`. The button appears automatically.

## Legal details (fill in before you take payments)

Set these variables; they appear on /terms, /privacy and /refunds. Indian e-commerce rules expect the seller's name, address and a grievance officer to be shown.

| Variable | Example |
|---|---|
| `FAULTSAGE_OPERATOR_NAME` | Your legal name or registered business name |
| `FAULTSAGE_OPERATOR_ADDRESS` | Postal address |
| `FAULTSAGE_GRIEVANCE_OFFICER` | Name of the person who handles complaints (can be you) |
| `FAULTSAGE_GRIEVANCE_EMAIL` | Email for complaints and privacy requests |
| `FAULTSAGE_JURISDICTION_CITY` | City for the courts clause, for example Kolkata |
| `FAULTSAGE_HOSTING_REGION` | Where your host and database run, for example Singapore |

The pages are drafts. Have a lawyer review them, and check GST registration needs with a tax adviser, before charging anyone.

## Taking payments (later)

Paid plans are off (`BILLING_PROVIDER=none`, decision D-017). When you choose a provider (Q-004 recommends Lemon Squeezy for a seller in India), set `BILLING_PROVIDER=lemonsqueezy`, `LEMONSQUEEZY_CHECKOUT_URL` and `LEMONSQUEEZY_WEBHOOK_SECRET`, and point the provider's webhook to `/api/v1/billing/webhook/lemonsqueezy`. The webhook checks the signature before changing any plan. Have the Terms and Privacy pages reviewed for your country before you charge anyone.

## Database changes in production

- Safe migrations apply automatically when the app starts.
- Destructive ones never do. The app refuses to start in production until a person approves them:
  ```bash
  faultsage-cloud db status
  faultsage-cloud db migrate --approve 3 --env production --approved-by "Your Name"
  ```
  It prints exactly what will be dropped, asks you to type `approve 0003 on production`, takes a `pg_dump` backup, runs it, and records the approval in `migration_approvals`. Approval covers that one migration in that one environment, once.

## Backups and restore

Two layers, both free:

1. **Your database provider's own history.** Neon keeps a restore window on every plan (its length on the free plan is shown in the Neon console under your project's settings). Use it for "undo the last few hours".
2. **Your own backup files**, which you keep. Take one every week and before every release. The image ships `pg_dump`, `pg_restore` and `psql` 17, which work with PostgreSQL 14 to 17 servers (tested against 16).

Take a backup from your Windows PC (needs Docker Desktop, the project folder, and your Neon connection string):

```powershell
docker build -t faultsage .
docker run --rm -v "${PWD}\backups:/bk" -e DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require" faultsage faultsage-cloud db backup --out-dir /bk
```

The file appears in the `backups` folder. It contains every customer's data: keep it on an encrypted disk, never commit it (`backups/` is in `.gitignore`), and delete old ones you no longer need.

Restore replaces **all** data with the backup. It is a destructive action, so it is gated like a destructive migration: it checks the file, asks you to type `restore <file> on production`, saves the current data to a new backup first, restores everything in one transaction (if anything fails, nothing changes), and records your name in `migration_approvals`.

```powershell
docker run --rm -it -v "${PWD}\backups:/bk" -e FAULTSAGE_ENV=production -e DATABASE_URL="..." faultsage faultsage-cloud db restore /bk/FILE.dump --env production --approved-by "Your Name" --backup-dir /bk
```

Practise a restore once on a spare Neon branch before you need it for real.

## After deploying

- Run the live check: GitHub, Actions, **live-check**, Run workflow, paste your address. It signs up, creates a project and key, sends a real error, pushes a case file, checks another customer cannot see it, and deletes its test accounts (`web/e2e/journey.mjs`).
- Run the launch checklist: `docs/security/05_LAUNCH-CHECKLIST.md`.
- In the CLI: `faultsage cloud login --url https://your-address` then `faultsage cloud push all`.
- In your app: see the Docs page (`/docs#sdk`) for the three lines that capture production errors.

#!/usr/bin/env bash
# CI: start a local daemon on the sample project and a cloud server, seed the cloud through its
# real API and SDK, then take screenshots of every screen and run axe (web/e2e/screens.mjs).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
bash "$root/tools/make_sample_project.sh" "$work/churn"
(cd "$work/churn" && python -m pytest -q >/dev/null 2>&1 || true)
(cd "$work/churn" && CI=1 faultsage watch --no-open --port 8765 > "$work/watch.log" 2>&1 &)
(cd "$work" && DATABASE_URL="sqlite:///$work/cloud.db" FAULTSAGE_BASE_URL=http://localhost:8000 \
  faultsage-cloud serve --port 8000 > "$work/cloud.log" 2>&1 &)
for i in $(seq 1 30); do curl -fs localhost:8000/healthz >/dev/null && [ -f "$work/churn/.faultsage/session" ] && break; sleep 1; done
python "$root/tools/seed_cloud.py" http://localhost:8000 "$work"
token="$(python -c "import json,sys;print(json.load(open(sys.argv[1]))['token'])" "$work/churn/.faultsage/session")"
cd "$root/web"
LOCAL_URL=http://127.0.0.1:8765 LOCAL_TOKEN="$token" CLOUD_URL=http://localhost:8000 \
  CLOUD_EMAIL=ana@example.com CLOUD_PASSWORD="correct horse battery staple" node e2e/screens.mjs
# Then the customer journey in a real browser: sign up, confirm email, sign in, project, API key,
# SDK error, CLI case file, tenant isolation, account deletion (web/e2e/journey.mjs).
BASE_URL=http://localhost:8000 PYTHON="$(command -v python)" VERIFY_LINK_CMD="cat $work/cloud.log" \
  OUT="$root/web/test-results/journey" node e2e/journey.mjs

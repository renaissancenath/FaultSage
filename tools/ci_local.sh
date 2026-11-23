#!/usr/bin/env bash
# Run the same checks as CI, offline, on Linux or WSL2. Usage: bash tools/ci_local.sh
set -u
failed=()
step() { local name="$1"; shift; echo; echo "== $name"; "$@" || failed+=("$name"); }

step "slop check" python3 tools/slop_check.py
step "contrast" python3 tools/slop_check.py --contrast

if [ -f pyproject.toml ]; then
  step ruff ruff check .
  step "ruff fmt" ruff format --check .
  step mypy mypy src
  step pytest pytest -q -m "not slow"
  step bandit bandit -q -r src -c pyproject.toml
  step pip-audit pip-audit --skip-editable
  step "api types" python3 tools/gen_api_types.py --check
  # Semgrep in its own venv: its pins conflict with FastAPI (opentelemetry-api).
  [ -x .semgrep-venv/bin/semgrep ] || { python3 -m venv .semgrep-venv && .semgrep-venv/bin/pip install -q semgrep; }
  step semgrep .semgrep-venv/bin/semgrep scan --config tools/semgrep --metrics=off --error
else
  echo "pyproject.toml not found: Python checks skipped (stage 1 not built yet)"
fi

if [ -f web/package.json ]; then
  (cd web && npm run lint && npm run typecheck && npm test && npm run build && npm audit --omit=dev --audit-level=high) || failed+=("web")
  step "screens + axe" bash tools/e2e_screens.sh
else
  echo "web/package.json not found: web checks skipped (stage 7 not built yet)"
fi

if [ ${#failed[@]} -gt 0 ]; then echo; echo "Failed: ${failed[*]}"; exit 1; fi
echo; echo "All checks passed"

# Run the same checks as CI, offline, on Windows PowerShell.
# Usage: .\tools\ci_local.ps1   (from the repo root, with .venv activated)
$ErrorActionPreference = "Stop"
$failed = @()

function Step($name, [scriptblock]$cmd) {
    Write-Host "`n== $name" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -ne 0) { $script:failed += $name }
}

Step "slop check" { python tools/slop_check.py }
Step "contrast"   { python tools/slop_check.py --contrast }

if (Test-Path pyproject.toml) {
    Step "ruff"       { ruff check . }
    Step "ruff fmt"   { ruff format --check . }
    Step "mypy"       { mypy src }
    Step "pytest"     { pytest -q -m "not slow" }
    Step "bandit"     { bandit -q -r src -c pyproject.toml }
    Step "pip-audit"  { pip-audit --skip-editable }
    Step "api types"  { python tools/gen_api_types.py --check }
    # Semgrep in its own venv: its pins conflict with FastAPI (opentelemetry-api).
    if (-not (Test-Path .semgrep-venv\Scripts\semgrep.exe)) { python -m venv .semgrep-venv; .semgrep-venv\Scripts\pip install -q semgrep }
    Step "semgrep"    { .semgrep-venv\Scripts\semgrep scan --config tools/semgrep --metrics=off --error }
} else { Write-Host "pyproject.toml not found: Python checks skipped (stage 1 not built yet)" }

if (Test-Path web/package.json) {
    Push-Location web
    Step "web lint"      { npm run lint }
    Step "web typecheck" { npm run typecheck }
    Step "web test"      { npm test }
    Step "web build"     { npm run build }
    Step "npm audit"     { npm audit --omit=dev --audit-level=high }
    Pop-Location
} else { Write-Host "web/package.json not found: web checks skipped (stage 7 not built yet)" }
Write-Host "`nScreenshots and axe: run bash tools/e2e_screens.sh inside WSL2 (needs Chromium + Playwright)."

if ($failed.Count -gt 0) { Write-Host "`nFailed: $($failed -join ', ')" -ForegroundColor Red; exit 1 }
Write-Host "`nAll checks passed" -ForegroundColor Green

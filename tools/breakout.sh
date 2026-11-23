#!/usr/bin/env bash
# Friday breakout: the whole local loop on a fresh project. Fails loudly on any wrong step.
# init -> failing pytest -> incident ranked with the real cause -> apply through the gate -> verify.
set -euo pipefail
work="$(mktemp -d)"
trap 'echo "Breakout workspace kept for inspection: $work"' EXIT
bash "$(dirname "$0")/make_sample_project.sh" "$work/churn"
cd "$work/churn"
python -m pytest -q >/dev/null 2>&1 && { echo "FAIL: sample test should fail"; exit 1; } || true
faultsage incidents | tee incidents.txt
grep -q "test_fit failed: KeyError" incidents.txt || { echo "FAIL: the failing test was not recorded"; exit 1; }
grep -qi "strong" incidents.txt && { echo "FAIL: Strong is switched off (D-024) but was shown"; exit 1; }
faultsage show I-1 > case.md
engine="$(python -c 'from faultsage.analysis.engine import NAME; print(NAME)')"
if [ "$engine" != "full" ]; then
  # Built-in engine: traceback ranking only, no patch rules for this failure (D-032).
  grep -q "src/churn/train.py:6" case.md || { echo "FAIL: expected the raise site train.py:6"; cat case.md; exit 1; }
  echo "Breakout passed (built-in engine): failure recorded and located. Ranking and patches need faultsage_engine."
  exit 0
fi
grep -q "src/churn/clean.py:4" case.md || { echo "FAIL: top cause should be clean.py:4"; cat case.md; exit 1; }
echo "wrong words" | faultsage apply S-1 >/dev/null 2>&1 && { echo "FAIL: apply must refuse without the typed confirmation"; exit 1; } || true
git diff --quiet || { echo "FAIL: files changed without approval"; exit 1; }
echo "apply S-1" | faultsage apply S-1 | tail -2
faultsage verify I-1
echo "Breakout passed: diagnosis, approval gate and verification work end to end."

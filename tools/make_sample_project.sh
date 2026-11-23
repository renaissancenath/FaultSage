#!/usr/bin/env bash
# Creates the renamed-column sample project used by the breakout check and screenshots.
# It is a behaviour fixture, not evaluation data: no metric is ever computed from it (TESTING.md 1).
set -euo pipefail
dest="${1:?usage: make_sample_project.sh DEST}"
mkdir -p "$dest/src/churn" "$dest/tests"
cd "$dest"
cat > pyproject.toml <<'TOML'
[project]
name = "churn"
version = "0.0.1"
[tool.pytest.ini_options]
pythonpath = ["src"]
TOML
: > src/churn/__init__.py
cat > src/churn/clean.py <<'PY'
def rename_columns(rows):
    out = []
    for r in rows:
        out.append({"customer": r["customer"], "transaction_amount": r["amt"]})
    return out
PY
cat > src/churn/train.py <<'PY'
from churn.clean import rename_columns


def build_matrix(rows):
    cleaned = rename_columns(rows)
    return [[r["customer"], r["transaction_amount"]] for r in cleaned]
PY
cat > tests/test_train.py <<'PY'
from churn.train import build_matrix


def test_fit():
    assert build_matrix([{"customer": "a", "amt": 3}]) == [["a", 3]]


def test_other():
    assert 1 + 1 == 2
PY
git init -q
git -c user.name=sample -c user.email=sample@example.com add -A
git -c user.name=sample -c user.email=sample@example.com commit -qm "Initial version"
sed -i 's/"transaction_amount": r\["amt"\]/"amount": r["amt"]/' src/churn/clean.py
git -c user.name=sample -c user.email=sample@example.com commit -qam "Rename column"
faultsage init --yes >/dev/null
git -c user.name=sample -c user.email=sample@example.com add -A
git -c user.name=sample -c user.email=sample@example.com commit -qm "Ignore FaultSage data"

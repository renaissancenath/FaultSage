"""SR-7, SR-11, SR-17 as source scans (backed up by Bandit and Semgrep in CI)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "faultsage"


def py_files() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "static" not in p.parts]


def test_no_shell_true_eval_exec_or_pickle() -> None:
    bad = re.compile(r"shell\s*=\s*True|\beval\(|\bexec\(|pickle\.loads?\(|os\.system\(")
    hits = [
        f"{p}:{i}"
        for p in py_files()
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if bad.search(line) and not line.strip().startswith("#")
    ]
    assert hits == []


def test_only_apply_gate_writes_project_files() -> None:
    """SR-11: writes outside .faultsage/ storage helpers live only in fixes/apply_gate.py."""
    write = re.compile(r"\.write_text\(|\.write_bytes\(|os\.replace\(|open\([^)]*['\"]w")
    allowed = {
        "fixes/apply_gate.py",
        "config/loader.py",
        "collectors/launcher.py",
        "cli/main.py",
        "cli/db_cmd.py",
        "storage/db.py",
        "daemon/ingest.py",
        "daemon/runner.py",
        "cloud_sync.py",
        "selfmon/hook.py",
        "bench/runner.py",
        "cli/bench_cmd.py",
        "api/routes/local.py",
    }
    offenders = [
        str(p.relative_to(SRC))
        for p in py_files()
        if write.search(p.read_text()) and str(p.relative_to(SRC)) not in allowed
    ]
    assert offenders == []


def test_web_never_injects_html() -> None:
    web = ROOT / "web" / "src"
    hits = [
        str(p)
        for p in web.rglob("*.tsx")
        if "dangerouslySetInnerHTML" in p.read_text() or "innerHTML" in p.read_text()
    ]
    assert hits == []

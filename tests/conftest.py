"""Shared fixtures.

The sample project below is a behaviour fixture (renamed column, as in docs/APP_FLOW.md flow 3).
It is never used for any metric: evaluation numbers come only from benchmark run records
(TESTING.md section 1).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from faultsage.analysis.engine import NAME as ENGINE

ROOT = Path(__file__).resolve().parent.parent

# Tests that check the ranking engine's specific answers run only where faultsage_engine is
# installed (its own CI runs this whole suite with it).
needs_engine = pytest.mark.skipif(ENGINE != "full", reason="needs the faultsage_engine package")


@pytest.fixture(autouse=True)
def _isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path_factory.mktemp("fshome")
    monkeypatch.setenv("FAULTSAGE_HOME", str(home))


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """A project whose test fails because clean.py renamed a column. FaultSage initialised."""
    dest = tmp_path / "churn"
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"}
    subprocess.run(
        ["bash", str(ROOT / "tools" / "make_sample_project.sh"), str(dest)],
        check=True,
        env=env,
        capture_output=True,
    )
    return dest


def run_pytest(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "faultsage"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=120,
    )

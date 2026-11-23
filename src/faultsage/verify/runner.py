"""Verify runner (F11, FR-25, FR-26, SR-8, SR-10).

Runs only ``sys.executable -m pytest <node ids>`` (ids validated) and commands the user wrote in
config. Results are recorded through the normal spool path by the FaultSage pytest plugin, and
also parsed from a JUnit XML report here so the verification row has per-test outcomes.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET  # nosec B405  our own pytest output only
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from faultsage.models.core import TestOutcome

NODE_ID = re.compile(r"^[\w./\\:\[\]-]+(::[\w\[\]\-.,= ]+)*$")


@dataclass(frozen=True, slots=True)
class VerifyRun:
    result: str  # resolved | still_failing | new_failures | timeout | error
    tests: list[TestOutcome]
    detail: str


def valid_node_ids(ids: list[str]) -> list[str]:
    return [i for i in ids if NODE_ID.match(i) and not i.startswith("-")]


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()


def _parse_junit(path: Path) -> list[TestOutcome]:
    if not path.exists():
        return []
    # Our own pytest run writes this file into a private temp dir; Python 3.12's expat blocks
    # entity expansion attacks, so defusedxml is not needed here.
    tree = ET.parse(path)  # noqa: S314  # nosec B314
    out: list[TestOutcome] = []
    for tc in tree.iter("testcase"):
        file_attr = tc.get("file")
        classname = tc.get("classname", "")
        name = tc.get("name", "")
        if file_attr:
            node = f"{file_attr}::{name}"
        else:
            parts = classname.split(".")
            node = "/".join(parts) + ".py::" + name if parts else name
        outcome: Literal["passed", "failed", "skipped", "error"] = "passed"
        if tc.find("failure") is not None:
            outcome = "failed"
        elif tc.find("error") is not None:
            outcome = "error"
        elif tc.find("skipped") is not None:
            outcome = "skipped"
        out.append(
            TestOutcome(node_id=node, outcome=outcome, duration_s=float(tc.get("time", 0) or 0))
        )
    return out


def classify(target_ids: list[str], tests: list[TestOutcome], returncode: int) -> str:
    if not tests:
        return "error" if returncode not in (0, 5) else "still_failing"
    failing_targets = [
        t
        for t in tests
        if any(t.node_id.endswith(tid.split("/")[-1]) or tid in t.node_id for tid in target_ids[:1])
    ]
    any_target_failed = any(t.outcome in ("failed", "error") for t in failing_targets)
    others_failed = any(t.outcome in ("failed", "error") for t in tests if t not in failing_targets)
    if any_target_failed:
        return "still_failing"
    if others_failed:
        return "new_failures"
    return "resolved"


def run_verify(
    root: Path, node_ids: list[str], timeout_s: int, extra_commands: list[list[str]] | None = None
) -> VerifyRun:
    ids = valid_node_ids(node_ids)
    if not ids:
        return VerifyRun("error", [], "No valid pytest node ids to run.")
    with tempfile.TemporaryDirectory(prefix="faultsage-verify-") as tmp:
        junit = Path(tmp) / "junit.xml"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            "-o",
            "junit_family=xunit1",
            *ids,
        ]
        popen_kw: dict[str, object] = {}
        if os.name == "posix":
            popen_kw["start_new_session"] = True
        proc = subprocess.Popen(
            cmd,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            **popen_kw,  # type: ignore[call-overload]
        )
        try:
            proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            proc.communicate()
            return VerifyRun("timeout", _parse_junit(junit), f"Timed out after {timeout_s} s.")
        tests = _parse_junit(junit)
        result = classify(ids, tests, proc.returncode)
    for extra in extra_commands or []:
        res = subprocess.run(
            extra,
            cwd=root,
            capture_output=True,
            timeout=timeout_s,
            check=False,
            shell=False,
        )
        tests.append(
            TestOutcome(
                node_id="cmd: " + " ".join(extra),
                outcome="passed" if res.returncode == 0 else "failed",
            )
        )
        if res.returncode != 0 and result == "resolved":
            result = "new_failures"
    passed = sum(t.outcome == "passed" for t in tests)
    return VerifyRun(result, tests, f"{passed} of {len(tests)} tests pass.")

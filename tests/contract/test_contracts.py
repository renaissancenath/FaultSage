"""Spool events and API models match BACKEND_SCHEMA.md; generated TS types are current."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from faultsage.models.events import validate_event

ROOT = Path(__file__).resolve().parents[2]


def test_spool_event_roundtrip() -> None:
    ev = validate_event(
        {
            "schema": "faultsage.event/1",
            "kind": "test_result",
            "occurred_at": "2026-12-01T09:14:03.120Z",
            "project_root": "C:/code/churn",
            "collector": "pytest_plugin",
            "collector_version": "0.1.0",
            "body": {"node_id": "tests/test_a.py::test_x", "phase": "call", "outcome": "failed"},
        }
    )
    assert ev.body["outcome"] == "failed"


@pytest.mark.parametrize(
    "bad",
    [
        {"schema": "other/1"},
        {"kind": "unknown_kind"},
        {"body": {"node_id": "x", "phase": "call", "outcome": "exploded"}},
        {"body": {"node_id": "x", "phase": "call", "outcome": "failed", "surprise": 1}},
    ],
)
def test_spool_event_rejects_invalid(bad: dict) -> None:  # type: ignore[type-arg]
    base = {
        "schema": "faultsage.event/1",
        "kind": "test_result",
        "project_root": "/p",
        "collector": "c",
        "collector_version": "1",
        "body": {"node_id": "x", "phase": "call", "outcome": "failed"},
    }
    with pytest.raises((ValidationError, KeyError)):
        validate_event({**base, **bad})


def test_generated_typescript_types_are_current() -> None:
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "gen_api_types.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout

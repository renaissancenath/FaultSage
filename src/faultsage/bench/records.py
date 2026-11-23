"""Read benchmark run records from results/runs (only these count as numbers, AGENTS.md 8)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def results_dir() -> Path:
    env = os.environ.get("FAULTSAGE_RESULTS")
    if env:
        return Path(env)
    repo = Path(__file__).resolve().parents[3]
    return repo / "results" / "runs"


def list_runs() -> list[dict[str, Any]]:
    d = results_dir()
    if not d.exists():
        return []
    out = []
    for run_json in sorted(d.glob("*/run.json"), reverse=True):
        try:
            data = json.loads(run_json.read_text(encoding="utf-8"))
        except ValueError:
            continue
        out.append(
            {
                k: data.get(k)
                for k in (
                    "run_id",
                    "dataset",
                    "dataset_version",
                    "split",
                    "cases_attempted",
                    "cases_reproduced",
                    "cases_excluded",
                    "started_at",
                    "finished_at",
                )
            }
        )
    return out


def get_run(run_id: str) -> dict[str, Any] | None:
    if "/" in run_id or "\\" in run_id or run_id.startswith("."):
        return None
    p = results_dir() / run_id / "run.json"
    if not p.exists():
        return None
    data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    cases_file = p.with_name("cases.jsonl")
    cases = []
    if cases_file.exists():
        for line in cases_file.read_text(encoding="utf-8").splitlines()[:5000]:
            try:
                cases.append(json.loads(line))
            except ValueError:
                continue
    data["cases"] = cases
    return data

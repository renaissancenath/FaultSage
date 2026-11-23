"""Picks the analysis engine.

The ranking engine is a separate package, ``faultsage_engine``. When it is installed, FaultSage
uses it. Otherwise the built-in ``basic`` engine runs: it ranks the frames of the traceback and
returns the same result shape, so the daemon, CLI, dashboard and cloud work the same either way.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from types import ModuleType

from faultsage.analysis import basic
from faultsage.analysis.types import AnalysisResult, GitHunks, Snapshot

__all__ = ["NAME", "AnalysisResult", "GitHunks", "Snapshot", "analyse", "installed_engine"]


def installed_engine() -> ModuleType | None:
    try:
        return importlib.import_module("faultsage_engine")
    except ModuleNotFoundError as e:
        if e.name != "faultsage_engine":
            raise  # the engine is installed but broken: say so instead of silently downgrading
        return None


_engine = installed_engine()
NAME = "full" if _engine else "basic"
analyse: Callable[..., AnalysisResult] = _engine.analyse if _engine else basic.analyse

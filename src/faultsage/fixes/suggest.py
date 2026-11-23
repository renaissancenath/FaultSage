"""Match rules against an analysed incident and return suggestions."""

from __future__ import annotations

from collections.abc import Callable
from importlib import metadata

from faultsage.analysis.engine import installed_engine
from faultsage.analysis.types import AnalysisResult
from faultsage.fixes.rules import basic
from faultsage.fixes.rules.base import Rule, RuleContext
from faultsage.models.core import ExceptionInfo, Suggestion

NODE_ID_LIMIT = 50


def rules() -> list[Rule]:
    engine = installed_engine()
    return list(engine.RULES) if engine else basic.RULES


def installed_version(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def verify_node_ids(failing_tests: list[str], analysis: AnalysisResult) -> list[str]:
    ids = list(dict.fromkeys(failing_tests))
    for imp in analysis.impacts:
        if imp.kind == "test" and imp.name.endswith(".py") and imp.name not in ids:
            ids.append(imp.name)
    return ids[:NODE_ID_LIMIT]


def suggest(
    exception: ExceptionInfo | None,
    analysis: AnalysisResult,
    failing_tests: list[str],
    read_file: Callable[[str], str | None],
) -> list[Suggestion]:
    if exception is None:
        return []
    ctx = RuleContext(
        exception,
        analysis,
        failing_tests,
        read_file,
        installed_version,
        verify_node_ids(failing_tests, analysis),
    )
    for rule in rules():
        if rule.match(ctx):
            return [rule.suggest(ctx)]
    return []

"""Fix rule interface (FR-22): ``match(ctx) -> bool`` and ``suggest(ctx) -> Suggestion``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from faultsage.analysis.types import AnalysisResult
from faultsage.models.core import ExceptionInfo, Suggestion


@dataclass(slots=True)
class RuleContext:
    exception: ExceptionInfo
    analysis: AnalysisResult
    failing_tests: list[str]
    read_file: Callable[[str], str | None]
    installed_version: Callable[[str], str | None]
    verify_node_ids: list[str] = field(default_factory=list)


class Rule(Protocol):
    rule_id: str

    def match(self, ctx: RuleContext) -> bool: ...

    def suggest(self, ctx: RuleContext) -> Suggestion: ...


def verify_cmd(node_ids: list[str]) -> str:
    return "python -m pytest " + " ".join(node_ids) if node_ids else ""


def explanation_only(rule_id: str, ctx: RuleContext, text: str) -> Suggestion:
    return Suggestion(
        rule_id=rule_id,
        explanation=text,
        patch_diff=None,
        verify_node_ids=ctx.verify_node_ids,
        verify_command=verify_cmd(ctx.verify_node_ids),
    )

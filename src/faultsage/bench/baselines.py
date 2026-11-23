"""Baselines run in the same run as FaultSage (DATASETS.md section 5, FR-34)."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

import networkx as nx

from faultsage.analysis.import_graph import module_name
from faultsage.analysis.sbfl import Spectrum, score_lines
from faultsage.models.core import ExceptionInfo


def top_frame(exc: ExceptionInfo | None) -> list[str]:
    if exc is None:
        return []
    seen: list[str] = []
    for f in reversed(exc.frames):
        if f.is_project and f.file_path not in seen:
            seen.append(f.file_path)
    return seen


def ochiai_files(spectrum: Spectrum | None, outcomes: Mapping[str, str]) -> list[str]:
    if spectrum is None:
        return []
    out: list[str] = []
    for ls in score_lines(spectrum, outcomes):
        if ls.file_path not in out:
            out.append(ls.file_path)
    return out


def recently_changed(changes: Mapping[str, int | None]) -> list[str]:
    return [p for p, _ in sorted(changes.items(), key=lambda kv: -(kv[1] or 0))]


def random_ranking(candidates: Sequence[str], seed: int) -> list[str]:
    c = list(candidates)
    random.Random(seed).shuffle(c)
    return c


def all_importers_tests(g: nx.DiGraph, root_file: str) -> set[str]:
    """Every test module that imports the root module directly or transitively."""
    root = module_name(root_file)
    if root not in g:
        return set()
    return {g.nodes[n].get("path", n) for n in nx.ancestors(g, root) if g.nodes[n].get("is_test")}

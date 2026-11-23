"""Pipeline graph from .faultsage/pipeline.toml. Edge producer -> consumer.

Known edges: a step's declared input equals another step's declared output.
Inferred edges: names differ but are similar (difflib ratio >= 0.8); always labelled inferred.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence

import networkx as nx


def as_list(value: object) -> list[object]:
    """Config and JSON values are untyped; treat anything that is not a list as empty."""
    return list(value) if isinstance(value, (list, tuple)) else []


def build_pipeline_graph(steps: Sequence[Mapping[str, object]]) -> nx.DiGraph:
    g: nx.DiGraph = nx.DiGraph()
    producers: dict[str, str] = {}
    for s in steps:
        name = str(s["name"])
        g.add_node(f"step:{name}", label=name, command=s.get("command"))
        for out in as_list(s.get("outputs")):
            producers[str(out)] = name
    for s in steps:
        name = str(s["name"])
        for raw_inp in as_list(s.get("inputs")):
            inp = str(raw_inp)
            if inp in producers:
                g.add_edge(f"step:{producers[inp]}", f"step:{name}", basis="known", artifact=inp)
                continue
            close = difflib.get_close_matches(inp, list(producers), n=1, cutoff=0.8)
            if close:
                g.add_edge(
                    f"step:{producers[close[0]]}",
                    f"step:{name}",
                    basis="inferred",
                    artifact=close[0],
                )
    return g


def dangling_inputs(steps: Sequence[Mapping[str, object]]) -> list[tuple[str, str]]:
    """Declared inputs that no step produces (scan rule)."""
    produced = {str(o) for s in steps for o in as_list(s.get("outputs"))}
    return [
        (str(s["name"]), str(i))
        for s in steps
        for i in as_list(s.get("inputs"))
        if str(i) not in produced
    ]


def upstream(g: nx.DiGraph, step: str) -> list[str]:
    node = f"step:{step}"
    if node not in g:
        return []
    return [n.removeprefix("step:") for n in nx.ancestors(g, node)]


def step_for_module(steps: Sequence[Mapping[str, object]], module: str) -> str | None:
    """Map a module to a declared step by its command (python -m module)."""
    for s in steps:
        cmd = s.get("command") or []
        if isinstance(cmd, list) and "-m" in cmd:
            i = cmd.index("-m")
            if i + 1 < len(cmd) and (
                module == cmd[i + 1]
                or module.endswith("." + str(cmd[i + 1]))
                or str(cmd[i + 1]).endswith("." + module.split(".")[-1])
            ):
                return str(s["name"])
    return None

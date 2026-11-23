"""Blast radius (FR-21): reverse BFS on the combined import and pipeline graph."""

from __future__ import annotations

from collections import deque

import networkx as nx

from faultsage.models.core import ImpactNode


def combined_graph(imports: nx.DiGraph, pipeline: nx.DiGraph) -> nx.DiGraph:
    """Return a graph where edge X -> Y means "Y depends on X" (failure in X reaches Y)."""
    g: nx.DiGraph = nx.DiGraph()
    for n, data in imports.nodes(data=True):
        g.add_node(n, kind="test" if data.get("is_test") else "module", path=data.get("path"))
    for a, b, data in imports.edges(data=True):
        g.add_edge(b, a, basis=data.get("basis", "known"))  # a imports b: b's failure reaches a
    for n, data in pipeline.nodes(data=True):
        g.add_node(n, kind="step", label=data.get("label"))
    for a, b, data in pipeline.edges(data=True):
        g.add_edge(a, b, basis=data.get("basis", "known"))
    return g


def blast_radius(
    g: nx.DiGraph, roots: list[str], max_depth: int = 4, covering_tests: set[str] | None = None
) -> list[ImpactNode]:
    seen: dict[str, tuple[int, str]] = {}
    queue: deque[tuple[str, int, str]] = deque((r, 0, "known") for r in roots if r in g)
    while queue:
        node, depth, basis = queue.popleft()
        if depth >= max_depth:
            continue
        for nxt in g.successors(node):
            edge_basis = g.edges[node, nxt].get("basis", "known")
            nb = "inferred" if "inferred" in (basis, edge_basis) else "known"
            d = depth + 1
            prev = seen.get(nxt)
            if nxt in roots or (prev and (prev[0] < d or (prev[0] == d and prev[1] == "known"))):
                continue
            seen[nxt] = (d, nb)
            queue.append((nxt, d, nb))
    out: list[ImpactNode] = []
    for node, (depth, basis) in seen.items():
        kind = g.nodes[node].get("kind", "module")
        name = (
            node.removeprefix("step:")
            if kind == "step"
            else (g.nodes[node].get("path") or node if kind == "test" else node)
        )
        out.append(
            ImpactNode(
                kind="step" if kind == "step" else ("test" if kind == "test" else "module"),
                name=str(name),
                relation="direct" if depth == 1 else "indirect",
                basis="inferred" if basis == "inferred" else "known",
                depth=depth,
            )
        )
    for t in sorted(covering_tests or set()):
        if not any(i.kind == "test" and t.startswith(i.name) for i in out):
            out.append(ImpactNode(kind="test", name=t, relation="direct", basis="known", depth=1))
    out.sort(key=lambda i: (i.depth, i.kind, i.name))
    return out

"""Import graph (FR-17) from AST import statements, resolving relative imports. Pure: callers
pass a mapping of relative POSIX path -> source text."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Mapping

import networkx as nx

from faultsage.analysis.pipeline_graph import as_list


def module_name(rel_path: str, source_roots: tuple[str, ...] = ("src",)) -> str:
    parts = rel_path[:-3].split("/") if rel_path.endswith(".py") else rel_path.split("/")
    for sr in source_roots:
        if parts and parts[0] == sr and len(parts) > 1:
            parts = parts[1:]
            break
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(source: str, mod: str, is_pkg: bool) -> set[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    out: set[str] = set()
    package = mod if is_pkg else mod.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".") if package else []
                if node.level > 1:
                    base_parts = base_parts[: len(base_parts) - (node.level - 1)]
                base = ".".join(p for p in base_parts if p)
                target = f"{base}.{node.module}" if node.module and base else (node.module or base)
            else:
                target = node.module or ""
            if target:
                out.add(target)
                for a in node.names:
                    out.add(f"{target}.{a.name}")
    return out


def files_hash(files: Mapping[str, str]) -> str:
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode())
        h.update(hashlib.sha256(files[path].encode("utf-8", "replace")).digest())
    return h.hexdigest()


def build_import_graph(files: Mapping[str, str]) -> nx.DiGraph:
    """Edge A -> B means module A imports module B. Node attribute ``path`` is the file."""
    g: nx.DiGraph = nx.DiGraph()
    mods: dict[str, str] = {}
    for path in files:
        mods[module_name(path)] = path
    for mod, path in mods.items():
        g.add_node(mod, path=path, is_test=_is_test(path))
    for mod, path in mods.items():
        for target in _imports(files[path], mod, path.endswith("__init__.py")):
            resolved = _resolve(target, mods)
            if resolved and resolved != mod:
                g.add_edge(mod, resolved, basis="known")
    return g


def _resolve(target: str, mods: Mapping[str, str]) -> str | None:
    t = target
    while t:
        if t in mods:
            return t
        t = t.rpartition(".")[0]
    # Tests often import by the last components only (conftest sys.path tricks).
    tail = target.split(".")[-1]
    matches = [m for m in mods if m.split(".")[-1] == tail]
    return matches[0] if len(matches) == 1 else None


def _is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{path}"


def hops(g: nx.DiGraph, src: str, dst: str) -> int | None:
    """Shortest import distance ignoring direction (a test imports the module or vice versa)."""
    if src not in g or dst not in g:
        return None
    try:
        return int(nx.shortest_path_length(g.to_undirected(as_view=True), src, dst))
    except nx.NetworkXNoPath:
        return None


def to_node_link(g: nx.DiGraph) -> dict[str, object]:
    return {
        "nodes": [{"id": n, **g.nodes[n]} for n in g.nodes],
        "edges": [{"source": a, "target": b, **g.edges[a, b]} for a, b in g.edges],
    }


def from_node_link(data: Mapping[str, object]) -> nx.DiGraph:
    g: nx.DiGraph = nx.DiGraph()
    for n in as_list(data.get("nodes")):
        node = dict(n) if isinstance(n, dict) else {}
        g.add_node(node.pop("id"), **node)
    for e in as_list(data.get("edges")):
        edge = dict(e) if isinstance(e, dict) else {}
        g.add_edge(edge.pop("source"), edge.pop("target"), **edge)
    return g


def find_cycles(g: nx.DiGraph, limit: int = 20) -> list[list[str]]:
    out: list[list[str]] = []
    for cycle in nx.simple_cycles(g):
        out.append(cycle)
        if len(out) >= limit:
            break
    return out

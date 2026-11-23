"""Deep scan rules (F3). Pure: inputs are file contents, installed module names and Ruff JSON."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from faultsage.analysis.import_graph import build_import_graph, find_cycles, module_name
from faultsage.analysis.pipeline_graph import dangling_inputs


def _top_level_imports(source: str) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((a.name.split(".")[0], node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.module.split(".")[0], node.lineno))
    return out


def scan(
    files: Mapping[str, str],
    installed_modules: Iterable[str],
    pipeline_steps: Sequence[Mapping[str, object]],
    ruff_findings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    project_tops = {module_name(p).split(".")[0] for p in files}
    project_tops |= {p.split("/")[0] for p in files}
    known = set(installed_modules) | set(sys.stdlib_module_names) | project_tops | {"__future__"}
    for path, src in sorted(files.items()):
        try:
            ast.parse(src)
        except SyntaxError as exc:
            findings.append(
                {
                    "severity": "error",
                    "rule": "syntax-error",
                    "file_path": path,
                    "line": exc.lineno,
                    "message": f"Syntax error: {exc.msg}",
                }
            )
            continue
        for top, line in _top_level_imports(src):
            if top not in known:
                findings.append(
                    {
                        "severity": "error",
                        "rule": "missing-dependency",
                        "file_path": path,
                        "line": line,
                        "message": f"Module {top} is imported but not installed in this environment",
                    }
                )
    graph = build_import_graph(files)
    for cycle in find_cycles(graph):
        first = graph.nodes[cycle[0]].get("path")
        findings.append(
            {
                "severity": "warning",
                "rule": "circular-import",
                "file_path": first,
                "line": None,
                "message": "Circular import: " + " -> ".join([*cycle, cycle[0]]),
            }
        )
    for step, inp in dangling_inputs(pipeline_steps):
        findings.append(
            {
                "severity": "warning",
                "rule": "pipeline-input",
                "file_path": ".faultsage/pipeline.toml",
                "line": None,
                "message": f"Step {step} reads {inp}, which no step produces",
            }
        )
    for f in ruff_findings or []:
        code = str(f.get("code") or "")
        if code.startswith(("F821", "F401", "F811", "F822", "F823", "E999")):
            findings.append(
                {
                    "severity": "error" if code in ("F821", "F822", "F823", "E999") else "note",
                    "rule": f"ruff-{code}",
                    "file_path": f.get("filename"),
                    "line": (f.get("location") or {}).get("row"),
                    "message": str(f.get("message", "")),
                }
            )
    return findings

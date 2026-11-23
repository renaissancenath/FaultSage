"""Built-in engine: ranks the frames of the traceback, innermost first.

This is what runs when the separate ranking engine (``faultsage_engine``) is not installed. It
uses only the traceback, so every cause is labelled Possible at most. The output has the same
shape as the full engine's, so the rest of FaultSage does not need to know which one ran.
"""

from __future__ import annotations

from faultsage.analysis.blast_radius import blast_radius, combined_graph
from faultsage.analysis.import_graph import build_import_graph, module_name
from faultsage.analysis.pipeline_graph import build_pipeline_graph, step_for_module
from faultsage.analysis.ranker import Weights, load_weights
from faultsage.analysis.types import AnalysisResult, Snapshot, SourceFiles, location, sha256_text
from faultsage.models.core import EvidenceItem, ExceptionInfo, Frame, Hypothesis, ImpactNode


def _is_test_file(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or any(p in ("test", "tests", "testing") for p in parts[:-1])
    )


def _failing_module(failing_tests: list[str], frames: list[Frame]) -> str | None:
    for t in failing_tests:
        path = t.split("::", 1)[0].replace("\\", "/")
        if path.endswith(".py"):
            return module_name(path)
    return module_name(frames[0].file_path) if frames else None


def analyse(
    exc: ExceptionInfo | None,
    failing_tests: list[str],
    snap: Snapshot,
    *,
    weights: Weights | None = None,
    blast_depth: int = 4,
    failing_step: str | None = None,
) -> AnalysisResult:
    w = weights or load_weights()
    files = SourceFiles(snap)
    imports = (
        snap.import_graph
        if snap.import_graph is not None
        else build_import_graph(
            {p: s for p in snap.python_files if (s := files.src(p)) is not None}
        )
    )
    pipeline = build_pipeline_graph(snap.pipeline_steps)
    frames = [f for f in (exc.frames if exc else []) if f.is_project]
    raise_site = (
        location(files, frames[-1].file_path, frames[-1].line, frames[-1].function)
        if frames
        else None
    )

    # Innermost first; code under test before the tests themselves.
    order = sorted(
        enumerate(reversed(frames)), key=lambda df: (_is_test_file(df[1].file_path), df[0])
    )
    seen: set[tuple[str, str]] = set()
    hyps: list[Hypothesis] = []
    hashes: dict[str, str] = {}
    for depth, f in order:
        if (f.file_path, f.function) in seen:
            continue
        seen.add((f.file_path, f.function))
        loc = location(files, f.file_path, f.line, f.function)
        src = files.src(f.file_path)
        if src is not None:
            hashes[f.file_path] = sha256_text(src)
        where = f"{f.file_path}:{f.line}" if f.line else f.file_path
        fn = f" in {loc.function}" if loc.function else ""
        claim = (
            f"{where}{fn} is where the exception was raised"
            if depth == 0
            else f"{where}{fn} is on the failure path"
        )
        hyps.append(
            Hypothesis(
                rank=len(hyps) + 1,
                score=round(1.0 / (1 + depth), 4),
                certainty="possible",
                claim=claim,
                location=loc,
                evidence=[
                    EvidenceItem(
                        source="traceback",
                        stance="supports",
                        summary=f"{where}{fn} is frame {len(frames) - depth} of {len(frames)} project frames",
                        detail={"depth_from_raise": depth, "is_project": True},
                    )
                ],
                weights_version=w.version,
                features={"tb_depth": round(1.0 / (1 + depth), 4)},
            )
        )
    if not hyps:
        hyps.append(
            Hypothesis(
                rank=1,
                score=0.0,
                certainty="unknown",
                claim="We do not have enough evidence to rank causes.",
                weights_version=w.version,
            )
        )

    root_node: str | None = None
    impacts: list[ImpactNode] = []
    top = hyps[0].location
    if top is not None:
        root_node = module_name(top.file_path)
        roots = [root_node]
        step = step_for_module(snap.pipeline_steps, root_node)
        if step:
            roots.append(f"step:{step}")
        impacts = blast_radius(combined_graph(imports, pipeline), roots, blast_depth, set())

    return AnalysisResult(
        raise_site=raise_site,
        hypotheses=hyps,
        impacts=impacts,
        missing_key=None,
        closest_matches=[],
        file_hashes=hashes,
        import_graph=imports,
        pipeline_graph=pipeline,
        failing_module=_failing_module(failing_tests, frames),
        root_node=root_node,
    )

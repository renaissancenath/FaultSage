from __future__ import annotations

from pathlib import Path

from faultsage.analysis.import_graph import (
    build_import_graph,
    files_hash,
    from_node_link,
    module_name,
    to_node_link,
)
from faultsage.analysis.pipeline_graph import (
    as_list,
    build_pipeline_graph,
    dangling_inputs,
    step_for_module,
    upstream,
)
from faultsage.analysis.sbfl import load_coverage_spectrum
from faultsage.analysis.scan import scan

STEPS = [
    {"name": "load", "command": ["python", "-m", "pipe.load"], "outputs": ["raw"]},
    {
        "name": "clean",
        "command": ["python", "-m", "pipe.clean"],
        "inputs": ["raw"],
        "outputs": ["clean_rows"],
    },
    {"name": "train", "command": ["python", "-m", "pipe.train"], "inputs": ["clean_row"]},
    {"name": "report", "inputs": ["nowhere"]},
]


def test_pipeline_graph_known_inferred_and_dangling() -> None:
    g = build_pipeline_graph(STEPS)
    assert g.edges["step:load", "step:clean"]["basis"] == "known"
    assert g.edges["step:clean", "step:train"]["basis"] == "inferred"
    assert ("report", "nowhere") in dangling_inputs(STEPS)
    assert set(upstream(g, "train")) == {"load", "clean"} and upstream(g, "missing") == []
    assert (
        step_for_module(STEPS, "pipe.clean") == "clean" and step_for_module(STEPS, "other") is None
    )
    assert as_list("x") == [] and as_list(("a",)) == ["a"]


def test_import_graph_relative_imports_and_roundtrip() -> None:
    files = {
        "src/pkg/__init__.py": "from . import a\n",
        "src/pkg/a.py": "from .b import thing\n",
        "src/pkg/b.py": "import os\nthing = 1\n",
        "tests/test_a.py": "from pkg.a import thing\n",
        "broken.py": "def (:\n",
    }
    g = build_import_graph(files)
    assert module_name("src/pkg/__init__.py") == "pkg"
    assert ("pkg.a", "pkg.b") in g.edges and ("tests.test_a", "pkg.a") in g.edges
    g2 = from_node_link(to_node_link(g))
    assert set(g2.edges) == set(g.edges) and g2.nodes["tests.test_a"]["is_test"]
    assert files_hash(files) == files_hash(dict(reversed(list(files.items()))))


def test_scan_rules() -> None:
    files = {
        "a.py": "import b\nimport notinstalled_pkg_xyz\n",
        "b.py": "import a\n",
        "bad.py": "def (:\n",
    }
    ruff = [
        {
            "code": "F821",
            "filename": "a.py",
            "location": {"row": 3},
            "message": "Undefined name `x`",
        },
        {"code": "F401", "filename": "a.py", "location": {"row": 1}, "message": "unused"},
        {"code": "E501", "filename": "a.py", "location": {"row": 1}, "message": "ignored"},
    ]
    found = scan(files, ["typer"], STEPS, ruff)
    rules = {f["rule"] for f in found}
    assert {
        "syntax-error",
        "missing-dependency",
        "circular-import",
        "pipeline-input",
        "ruff-F821",
        "ruff-F401",
    } <= rules
    assert "ruff-E501" not in rules


def test_ochiai_from_a_real_coverage_data_file(tmp_path: Path) -> None:
    from coverage import CoverageData

    data_file = tmp_path / ".coverage"
    cd = CoverageData(basename=str(data_file))
    src = str(tmp_path / "m.py")
    cd.set_context("tests/test_m.py::test_bad|run")
    cd.add_lines({src: [1, 2]})
    cd.set_context("tests/test_m.py::test_good|run")
    cd.add_lines({src: [1]})
    cd.write()
    sp = load_coverage_spectrum(str(data_file), lambda f: "m.py" if f == src else None)
    assert sp is not None
    assert sp.covered[("m.py", 2)] == {"tests/test_m.py::test_bad"}
    assert load_coverage_spectrum(str(tmp_path / "missing"), lambda f: f) is None

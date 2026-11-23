from __future__ import annotations

from pathlib import Path

import pytest

from faultsage.analysis.ranker import Weights, certainty_for, load_weights, train_logistic
from faultsage.analysis.sbfl import Spectrum, ochiai, score_lines
from faultsage.bench.metrics import exam, precision_recall, summarise, topk
from faultsage.errors import PathOutsideProjectError
from faultsage.models.core import EvidenceItem, TestOutcome
from faultsage.paths import inside_root
from faultsage.verify.runner import classify, valid_node_ids


def ev(source: str, stance: str = "supports") -> EvidenceItem:
    return EvidenceItem(source=source, stance=stance, summary="x")  # type: ignore[arg-type]


def test_certainty_rules() -> None:
    w = Weights("t", 0.0, {}, strong_margin=0.15, strong_min_sources=2, strong_enabled=True)
    assert certainty_for(1, 0.9, 0.2, [], w) == "unknown"
    assert certainty_for(1, 0.9, 0.2, [ev("git"), ev("traceback")], w) == "strong"
    assert (
        certainty_for(1, 0.9, 0.85, [ev("git"), ev("traceback")], w) == "possible"
    )  # small margin
    assert (
        certainty_for(1, 0.9, 0.2, [ev("git"), ev("traceback"), ev("git", "contradicts")], w)
        == "possible"
    )
    assert certainty_for(2, 0.9, 0.2, [ev("git"), ev("traceback")], w) == "possible"


def test_shipped_weights_withhold_strong() -> None:
    """D-024 (Q-009): shipped weights never say Strong until a held-out run earns it."""
    w = load_weights()
    assert w.strong_enabled is False
    assert certainty_for(1, 0.9, 0.2, [ev("git"), ev("traceback")], w) == "possible"


def test_ochiai_formula() -> None:
    assert ochiai(1, 0, 0) == 1.0
    assert ochiai(0, 3, 1) == 0.0
    sp = Spectrum(covered={("a.py", 1): {"t1", "t2"}, ("a.py", 2): {"t2"}})
    lines = score_lines(sp, {"t1": "failed", "t2": "passed"})
    assert lines[0].line == 1 and round(lines[0].ochiai, 3) == round(1 / (1 * 2) ** 0.5, 3)


def test_metrics() -> None:
    assert topk(["a", "b"], ["b"], 1) == 0 and topk(["a", "b"], ["b"], 3) == 1
    assert exam(["a", "b"], ["b"], 4) == 0.5
    assert precision_recall({"a", "b"}, {"b"}) == (0.5, 1.0)
    s = summarise(
        [
            {
                "reproduced": True,
                "truth": {"files": ["x"]},
                "predictions": {"faultsage": {"files": ["x"]}},
            },
            {"reproduced": False, "truth": {"files": ["y"]}},
        ]
    )
    assert s["n"] == 1 and s["methods"]["faultsage"]["top1"]["mean"] == 1.0


def test_logistic_learns_a_separable_feature() -> None:
    rows = [({"ochiai": 1.0}, 1)] * 10 + [({"ochiai": 0.0}, 0)] * 10
    _, w = train_logistic(rows, epochs=200, lr=0.5)
    assert w["ochiai"] > 0.5


def test_paths_stay_inside_root(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("")
    assert inside_root(tmp_path, "a.py") == (tmp_path / "a.py").resolve()
    with pytest.raises(PathOutsideProjectError):
        inside_root(tmp_path, "../outside.py")
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("x")
    (tmp_path / "link.py").symlink_to(outside)
    with pytest.raises(PathOutsideProjectError):
        inside_root(tmp_path, "link.py")


def test_node_ids_reject_injection() -> None:
    assert valid_node_ids(
        [
            "tests/test_a.py::test_x",
            "tests/test_a.py::test_p[1-2]",
            "--co",
            "a.py; rm -rf /",
            "-p evil",
        ]
    ) == ["tests/test_a.py::test_x", "tests/test_a.py::test_p[1-2]"]


def test_classify_verification() -> None:
    t = [TestOutcome(node_id="tests/test_a.py::test_x", outcome="passed")]
    assert classify(["tests/test_a.py::test_x"], t, 0) == "resolved"
    t2 = [TestOutcome(node_id="tests/test_a.py::test_x", outcome="failed")]
    assert classify(["tests/test_a.py::test_x"], t2, 1) == "still_failing"
    t3 = [*t, TestOutcome(node_id="tests/test_b.py::test_y", outcome="failed")]
    assert classify(["tests/test_a.py::test_x"], t3, 1) == "new_failures"

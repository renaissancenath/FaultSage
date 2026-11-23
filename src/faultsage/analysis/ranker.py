"""Ranker (FR-19) and certainty labels (FR-20)."""

from __future__ import annotations

import importlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from faultsage.models.core import Certainty, EvidenceItem

FEATURES = (
    "tb_depth",
    "ochiai",
    "changed_recently",
    "schema_mismatch",
    "import_distance",
    "recurrence",
)
WEIGHTS_FILE = Path(__file__).with_name("weights.json")


@dataclass(frozen=True, slots=True)
class Weights:
    version: str
    bias: float
    weights: dict[str, float]
    strong_margin: float
    strong_min_sources: int
    # Strong is withheld until a held-out test run shows >= 75% Strong precision (D-024).
    strong_enabled: bool = True


def weights_file() -> Path:
    """The trained weights of the installed engine, or the built-in ones."""
    try:
        engine = importlib.import_module("faultsage_engine")
    except ModuleNotFoundError as e:
        if e.name != "faultsage_engine":
            raise
        return WEIGHTS_FILE
    return Path(engine.WEIGHTS_FILE)


@lru_cache(maxsize=4)
def load_weights(path: Path | None = None) -> Weights:
    data = json.loads((path or weights_file()).read_text(encoding="utf-8"))
    return Weights(
        version=str(data["version"]),
        bias=float(data["bias"]),
        weights={k: float(v) for k, v in data["weights"].items()},
        strong_margin=float(data.get("strong_margin", 0.15)),
        strong_min_sources=int(data.get("strong_min_sources", 2)),
        strong_enabled=bool(data.get("strong_enabled", True)),
    )


def score(features: dict[str, float], w: Weights) -> float:
    z = w.bias + sum(w.weights.get(k, 0.0) * features.get(k, 0.0) for k in FEATURES)
    return 1.0 / (1.0 + math.exp(-z))


def independent_sources(evidence: list[EvidenceItem]) -> set[str]:
    return {e.source for e in evidence if e.stance == "supports"}


def certainty_for(
    rank: int,
    score_value: float,
    next_score: float | None,
    evidence: list[EvidenceItem],
    w: Weights,
) -> Certainty:
    sources = independent_sources(evidence)
    if not sources:
        return "unknown"
    margin = score_value - (next_score if next_score is not None else 0.0)
    contradicted = any(e.stance == "contradicts" for e in evidence)
    if (
        w.strong_enabled
        and rank == 1
        and not contradicted
        and margin >= w.strong_margin
        and len(sources) >= w.strong_min_sources
    ):
        return "strong"
    return "possible"


def train_logistic(
    rows: list[tuple[dict[str, float], int]], epochs: int = 400, lr: float = 0.1, l2: float = 0.01
) -> tuple[float, dict[str, float]]:
    """Plain gradient-descent logistic regression for the dev split (no extra dependency)."""
    bias = 0.0
    weights = dict.fromkeys(FEATURES, 0.0)
    n = max(len(rows), 1)
    for _ in range(epochs):
        gb = 0.0
        gw = dict.fromkeys(FEATURES, 0.0)
        for feats, label in rows:
            z = bias + sum(weights[k] * feats.get(k, 0.0) for k in FEATURES)
            p = 1.0 / (1.0 + math.exp(-z))
            err = p - label
            gb += err
            for k in FEATURES:
                gw[k] += err * feats.get(k, 0.0)
        bias -= lr * gb / n
        for k in FEATURES:
            weights[k] -= lr * (gw[k] / n + l2 * weights[k])
    return bias, weights

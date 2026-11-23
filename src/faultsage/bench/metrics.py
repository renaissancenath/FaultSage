"""Evaluation metrics (TESTING.md section 5). Computed from cases.jsonl only, so anyone can
recompute them."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any


def topk(pred: Sequence[str], truth: Sequence[str], k: int) -> int:
    t = set(truth)
    return int(any(p in t for p in pred[:k]))


def exam(pred: Sequence[str], truth: Sequence[str], n_candidates: int) -> float | None:
    t = set(truth)
    for i, p in enumerate(pred):
        if p in t:
            return (i + 1) / max(n_candidates, 1)
    return None


def precision_recall(pred: set[str], actual: set[str]) -> tuple[float, float]:
    if not pred and not actual:
        return 1.0, 1.0
    tp = len(pred & actual)
    return (tp / len(pred) if pred else 0.0, tp / len(actual) if actual else 0.0)


def bootstrap_ci(values: Sequence[float], n: int = 1000, seed: int = 7) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(n))
    return (means[int(0.025 * n)], means[int(0.975 * n) - 1])


def summarise(cases: list[dict[str, Any]], level: str = "files") -> dict[str, Any]:
    reproduced = [c for c in cases if c.get("reproduced")]
    methods = sorted({m for c in reproduced for m in c.get("predictions", {})})
    out: dict[str, Any] = {"n": len(reproduced), "methods": {}}
    for m in methods:
        res: dict[str, Any] = {}
        for k in (1, 3, 5):
            vals = []
            for c in reproduced:
                pred = c["predictions"].get(m)
                if pred is None:
                    continue
                if "files_by_seed" in pred:  # random baseline: mean over its seeds
                    seeds = pred["files_by_seed"] or [[]]
                    vals.append(sum(topk(s, c["truth"][level], k) for s in seeds) / len(seeds))
                else:
                    vals.append(float(topk(pred.get(level, []), c["truth"][level], k)))
            mean = sum(vals) / len(vals) if vals else 0.0
            lo, hi = bootstrap_ci(vals)
            res[f"top{k}"] = {"mean": round(mean, 4), "ci95": [round(lo, 4), round(hi, 4)]}
        out["methods"][m] = res
    br = [c["blast_radius"] for c in reproduced if c.get("blast_radius")]
    if br:
        ps, rs = zip(
            *(
                precision_recall(set(b["predicted_tests"]), set(b["actual_failing_tests"]))
                for b in br
            ),
            strict=False,
        )
        out["blast_radius"] = {
            "precision": round(sum(ps) / len(ps), 4),
            "recall": round(sum(rs) / len(rs), 4),
        }
    vc = [c["verify"] for c in reproduced if c.get("verify")]
    if vc:
        ok = sum(
            1 for v in vc if v.get("buggy") == "still_failing" and v.get("fixed") == "resolved"
        )
        out["verify_correctness"] = round(ok / len(vc), 4)
    return out

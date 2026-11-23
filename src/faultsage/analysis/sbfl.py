"""Spectrum-based fault localisation (FR-18): Ochiai = ef / sqrt((ef + nf) * (ef + ep))."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(slots=True)
class Spectrum:
    """Per-line test coverage. ``covered[(file, line)]`` is the set of test ids covering it."""

    covered: dict[tuple[str, int], set[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LineScore:
    file_path: str
    line: int
    ochiai: float
    ef: int
    ep: int
    nf: int
    np: int


def ochiai(ef: int, ep: int, nf: int) -> float:
    denom = math.sqrt((ef + nf) * (ef + ep))
    return ef / denom if denom else 0.0


def score_lines(spectrum: Spectrum, outcomes: Mapping[str, str]) -> list[LineScore]:
    failing = {t for t, o in outcomes.items() if o in ("failed", "error")}
    passing = {t for t, o in outcomes.items() if o == "passed"}
    total_f, total_p = len(failing), len(passing)
    out: list[LineScore] = []
    for (path, line), tests in spectrum.covered.items():
        ef = len(tests & failing)
        ep = len(tests & passing)
        if ef == 0:
            continue
        nf = total_f - ef
        np_ = total_p - ep
        out.append(LineScore(path, line, ochiai(ef, ep, nf), ef, ep, nf, np_))
    out.sort(key=lambda s: (-s.ochiai, s.file_path, s.line))
    return out


def load_coverage_spectrum(data_file: str, to_rel: object) -> Spectrum | None:
    """Read a coverage.py data file recorded with ``--cov-context=test``.

    ``to_rel`` maps absolute file names to project-relative POSIX paths, or returns None for
    files outside the project.
    """
    try:
        from coverage import CoverageData
    except ImportError:
        return None
    data = CoverageData(basename=data_file, read_only=True)
    try:
        data.read()
    except Exception:
        return None
    spectrum = Spectrum()
    for filename in data.measured_files():
        rel = to_rel(filename)  # type: ignore[operator]
        if rel is None:
            continue
        for line, contexts in data.contexts_by_lineno(filename).items():
            tests = {c.split("|", 1)[0] for c in contexts if c}
            if tests:
                spectrum.covered[(rel, int(line))] = tests
    return spectrum if spectrum.covered else None

"""Data passed into and out of an analysis engine.

Both engines (the built-in ``basic`` one and the separately installed ``faultsage_engine``)
read a ``Snapshot`` and return an ``AnalysisResult``, so the daemon, CLI and cloud do not care
which one ran.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import networkx as nx

from faultsage.analysis.ast_index import FileIndex, excerpt, index_source
from faultsage.analysis.sbfl import Spectrum
from faultsage.models.core import EvidenceItem, Hypothesis, ImpactNode, Location


@dataclass(frozen=True, slots=True)
class GitHunks:
    hunks: tuple[tuple[int, int], ...]
    commit_time: int | None


@dataclass(slots=True)
class Snapshot:
    """Everything the engine may read about the project, provided by the caller."""

    read_file: Callable[[str], str | None]
    python_files: list[str]
    git_changes: Mapping[str, GitHunks] = field(default_factory=dict)
    checkpoints: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    pipeline_steps: Sequence[Mapping[str, object]] = field(default_factory=list)
    spectrum: Spectrum | None = None
    test_outcomes: Mapping[str, str] = field(default_factory=dict)
    prior_incidents: Callable[[str], list[int]] = lambda _p: []
    import_graph: nx.DiGraph | None = None
    now: float = field(default_factory=time.time)


@dataclass(slots=True)
class Candidate:
    file_path: str
    line: int | None
    function: str | None
    class_name: str | None = None
    pipeline_step: str | None = None
    features: dict[str, float] = field(default_factory=dict)
    evidence: list[EvidenceItem] = field(default_factory=list)
    claim: str = ""

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.file_path, self.function)


@dataclass(slots=True)
class AnalysisResult:
    raise_site: Location | None
    hypotheses: list[Hypothesis]
    impacts: list[ImpactNode]
    missing_key: str | None
    closest_matches: list[str]
    file_hashes: dict[str, str]
    import_graph: nx.DiGraph
    pipeline_graph: nx.DiGraph
    failing_module: str | None
    root_node: str | None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


class SourceFiles:
    """Reads and indexes project files once per analysis."""

    def __init__(self, snap: Snapshot) -> None:
        self.snap = snap
        self._src: dict[str, str | None] = {}
        self._idx: dict[str, FileIndex] = {}

    def src(self, path: str) -> str | None:
        if path not in self._src:
            self._src[path] = self.snap.read_file(path)
        return self._src[path]

    def index(self, path: str) -> FileIndex | None:
        s = self.src(path)
        if s is None:
            return None
        if path not in self._idx:
            self._idx[path] = index_source(s)
        return self._idx[path]


def location(files: SourceFiles, path: str, line: int | None, function: str | None) -> Location:
    src = files.src(path)
    if src is None or line is None:
        return Location(file_path=path, line=None, function=function, available=False)
    n_lines = src.count("\n") + 1
    if line < 1 or line > n_lines:
        return Location(file_path=path, line=None, function=function, available=False)
    idx = files.index(path)
    fn = idx.enclosing(line) if idx else None
    return Location(
        file_path=path,
        line=line,
        function=fn.qualname if fn else (function if function not in (None, "<unknown>") else None),
        class_name=fn.class_name if fn else None,
        excerpt=excerpt(src, line),
        available=True,
    )

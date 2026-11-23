"""Workspace: the daemon's state for one project, and the service functions the CLI and API call.

Routes never run SQL or business logic themselves (ARCHITECTURE section 8, rule 4).
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Literal

from faultsage.analysis.engine import GitHunks, Snapshot, analyse
from faultsage.analysis.import_graph import (
    build_import_graph,
    files_hash,
    from_node_link,
    to_node_link,
)
from faultsage.analysis.pipeline_graph import build_pipeline_graph
from faultsage.analysis.sbfl import load_coverage_spectrum
from faultsage.analysis.scan import scan as run_scan_rules
from faultsage.collectors import git_reader
from faultsage.collectors.frames import is_project_path
from faultsage.config.loader import ProjectPaths, config_hash, load, load_pipeline
from faultsage.config.model import Config
from faultsage.errors import NotFoundError, VerifyRunningError
from faultsage.fixes.apply_gate import apply_suggestion
from faultsage.fixes.patch import sha256_text
from faultsage.fixes.suggest import suggest
from faultsage.models.core import (
    Approval,
    CaseFile,
    ExceptionInfo,
    Graph,
    GraphEdge,
    GraphNode,
    IncidentSummary,
    Verification,
)
from faultsage.paths import inside_root, list_python_files, to_posix_rel
from faultsage.selfmon import hook as selfmon
from faultsage.storage import repo_events, repo_incidents
from faultsage.storage.db import ConnectionPerThread, open_store, tx
from faultsage.verify.runner import run_verify

_log = logging.getLogger("faultsage.daemon")
MAX_FILES = 5000


@dataclass
class Workspace:
    paths: ProjectPaths
    cfg: Config
    pool: Any
    project_id: int
    session_id: int | None = None
    state: str = "stopped"
    started_at: float = field(default_factory=time.time)
    test_outcomes: dict[str, str] = field(default_factory=dict)
    listeners: list[Callable[[dict[str, Any]], None]] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)
    _head_cache: tuple[float, str | None] = (0.0, None)

    @property
    def conn(self) -> Any:
        """The calling thread's own connection."""
        return self.pool.get()

    # ---- lifecycle -------------------------------------------------------------------------
    @classmethod
    def open(cls, paths: ProjectPaths, approve: set[int] | None = None) -> Workspace:
        cfg = load(paths)
        paths.ensure()
        open_store(paths.db, approve).close()  # migrate once, then one connection per thread
        pool = ConnectionPerThread(paths.db)
        conn = pool.get()
        with tx(conn):
            pid = repo_events.upsert_project(
                conn,
                cfg.project.name,
                paths.root.as_posix(),
                platform.python_version(),
                config_hash(paths),
            )
        ws = cls(paths=paths, cfg=cfg, pool=pool, project_id=pid)
        with tx(conn):
            repo_events.delete_old_events(conn, pid, cfg.retention.event_days)
        return ws

    def emit(self, type_: str, payload: dict[str, Any]) -> None:
        for fn in list(self.listeners):
            try:
                fn({"type": type_, "payload": payload})
            except Exception:
                _log.debug("listener failed", exc_info=True)

    def git_head(self) -> str | None:
        ts, head = self._head_cache
        if time.time() - ts > 5 and self.cfg.signals.git:
            head, _ = git_reader.head(self.paths.root)
            self._head_cache = (time.time(), head)
        return head

    def status(self) -> dict[str, Any]:
        head, branch = git_reader.head(self.paths.root) if self.cfg.signals.git else (None, None)
        sig = self.cfg.signals
        return {
            "state": self.state,
            "project": self.cfg.project.name,
            "root": self.paths.root.as_posix(),
            "since": self.started_at,
            "open_incidents": repo_incidents.count_open(self.conn, self.project_id),
            "signals": {
                "pytest": sig.pytest,
                "run_wrapper": sig.run_wrapper,
                "git": sig.git,
                "file_watch": sig.file_watch,
                "logs": bool(sig.logs),
            },
            "git": {"head": head, "branch": branch},
            "python": platform.python_version(),
            "tests_found": self._count_tests(),
            "weights": _weights_version(),
            "cloud": {"enabled": self.cfg.cloud.enabled, "url": self.cfg.cloud.url},
        }

    def _count_tests(self) -> int:
        return sum(1 for p in self.python_files() if p.rsplit("/", 1)[-1].startswith("test_"))

    # ---- project reading --------------------------------------------------------------------
    def python_files(self) -> list[str]:
        return list_python_files(self.paths.root, MAX_FILES)

    def read_file(self, rel: str) -> str | None:
        if rel.startswith("<"):
            return None
        try:
            p = inside_root(self.paths.root, rel)
            return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        except (OSError, ValueError, Exception):
            return None

    def import_graph(self) -> Any:
        files = {p: s for p in self.python_files() if (s := self.read_file(p)) is not None}
        fh = files_hash(files)
        cached = repo_events.load_graph(self.conn, self.project_id, "imports")
        if cached and cached[0] == fh:
            return from_node_link(cached[1])
        g = build_import_graph(files)
        with tx(self.conn):
            repo_events.save_graph(self.conn, self.project_id, "imports", fh, to_node_link(g))
        return g

    def snapshot(self) -> Snapshot:
        changes: dict[str, GitHunks] = {}
        if self.cfg.signals.git and git_reader.is_repo(self.paths.root):
            for path, ch in git_reader.recent_changes(self.paths.root).items():
                changes[path] = GitHunks(tuple(ch.hunks), ch.commit_time)
        spectrum = None
        if self.cfg.analysis.coverage_contexts:
            cov = self.paths.root / ".coverage"
            if cov.exists():

                def to_rel(f: str) -> str | None:
                    return (
                        to_posix_rel(self.paths.root, f)
                        if is_project_path(self.paths.root, f)
                        else None
                    )

                spectrum = load_coverage_spectrum(str(cov), to_rel)
        return Snapshot(
            read_file=self.read_file,
            python_files=self.python_files(),
            git_changes=changes,
            checkpoints=repo_events.latest_checkpoints(self.conn, self.project_id),
            pipeline_steps=load_pipeline(self.paths),
            spectrum=spectrum,
            test_outcomes=dict(self.test_outcomes),
            import_graph=self.import_graph(),
        )

    # ---- analysis ---------------------------------------------------------------------------
    def analyse_incident(self, incident_id: int) -> None:
        inc = repo_incidents.get_incident(self.conn, incident_id)
        if inc is None:
            raise NotFoundError(f"Incident I-{incident_id} not found.")
        occ = repo_incidents.occurrence_events(self.conn, incident_id)
        exc = None
        failing: list[str] = []
        for o in occ:
            p = o["payload"]
            if exc is None and p.get("exception"):
                exc = ExceptionInfo.model_validate(p["exception"])
            if p.get("node_id") and p["node_id"] not in failing:
                failing.append(p["node_id"])
        if exc is None and occ:
            from faultsage.analysis.traceback_parser import parse_any

            p = occ[-1]["payload"]
            text = p.get("longrepr_text") or p.get("stderr_tail") or p.get("text") or ""
            exc = parse_any(
                text, lambda f: is_project_path(self.paths.root, str(self.paths.root / f))
            )
        try:
            snap = self.snapshot()
            snap.prior_incidents = lambda path: repo_incidents.prior_incidents_at(
                self.conn, self.project_id, path, incident_id
            )
            result = analyse(exc, failing, snap, blast_depth=self.cfg.analysis.blast_radius_depth)
            suggestions = suggest(exc, result, failing, self.read_file)
            raise_hash = None
            if (
                result.raise_site
                and (src := self.read_file(result.raise_site.file_path)) is not None
            ):
                raise_hash = sha256_text(src)
            with tx(self.conn):
                repo_incidents.replace_analysis(
                    self.conn,
                    incident_id,
                    result.raise_site,
                    raise_hash,
                    result.hypotheses,
                    result.impacts,
                    suggestions,
                    result.file_hashes,
                )
                repo_incidents.set_analysis_error(self.conn, incident_id, None)
                if suggestions and inc["status"] in ("open", "reopened"):
                    repo_incidents.set_status(self.conn, incident_id, "fix_proposed")
        except Exception as e:
            selfmon.record(e, "analysis", {"incident": incident_id})
            with tx(self.conn):
                repo_incidents.set_analysis_error(
                    self.conn,
                    incident_id,
                    f"Analysis failed: {type(e).__name__}. Recorded in self-monitoring.",
                )
        self.emit("incident.updated", {"id": incident_id, "status": self._status_of(incident_id)})

    def _status_of(self, incident_id: int) -> str:
        r = repo_incidents.get_incident(self.conn, incident_id)
        return str(r["status"]) if r else "unknown"

    def ingest(self) -> None:
        from faultsage.daemon.ingest import ingest_once

        with self.lock:
            res = ingest_once(self)
            for iid in sorted(res.touched_incidents):
                self.analyse_incident(iid)
                if iid in res.created_incidents:
                    s = repo_incidents.summary(self.conn, iid)
                    if s:
                        self.emit("incident.created", s.model_dump(mode="json"))
            if res.touched_incidents and self.cfg.cloud.enabled:
                from faultsage.cloud_sync import push_incidents

                push_incidents(self, sorted(res.touched_incidents))

    # ---- queries ----------------------------------------------------------------------------
    def list_incidents(
        self, status: str | None, q: str | None, limit: int, cursor: int | None
    ) -> tuple[list[IncidentSummary], int | None]:
        return repo_incidents.list_incidents(self.conn, self.project_id, status, q, limit, cursor)

    def case_file(self, incident_id: int) -> CaseFile:
        cf = repo_incidents.case_file(self.conn, incident_id)
        if cf is None:
            raise NotFoundError(
                f"Incident I-{incident_id} not found.", "Check the id in the Incidents list."
            )
        # Mark suggestions stale if the file changed (FR-23); location honesty for changed files.
        for s in cf.suggestions:
            if s.state == "proposed" and s.base_hashes:
                for path, h in s.base_hashes.items():
                    src = self.read_file(path)
                    if src is None or sha256_text(src) != h:
                        s.state = "stale"
                        with tx(self.conn):
                            repo_incidents.set_suggestion_state(self.conn, s.id, "stale")
        return cf

    def set_incident_status(self, incident_id: int, status: str) -> IncidentSummary:
        if repo_incidents.get_incident(self.conn, incident_id) is None:
            raise NotFoundError(f"Incident I-{incident_id} not found.")
        with tx(self.conn):
            repo_incidents.set_status(self.conn, incident_id, status)
        self.emit("incident.updated", {"id": incident_id, "status": status})
        s = repo_incidents.summary(self.conn, incident_id)
        if s is None:
            raise NotFoundError(f"Incident I-{incident_id} not found.")
        return s

    def graph(self, kind: str, focus: int | None) -> Graph:
        failing_mods: set[str] = set()
        path_nodes: set[str] = set()
        cf = repo_incidents.case_file(self.conn, focus) if focus else None
        if kind == "pipeline":
            g = build_pipeline_graph(load_pipeline(self.paths))
            nodes = [
                GraphNode(id=n, label=str(d.get("label", n)), kind="step")
                for n, d in g.nodes(data=True)
            ]
            edges = [
                GraphEdge(source=a, target=b, basis=d.get("basis", "known"))
                for a, b, d in g.edges(data=True)
            ]
            if cf:
                steps = {f"step:{i.name}" for i in cf.impacts if i.kind == "step"}
                top = next((h.pipeline_step for h in cf.hypotheses if h.pipeline_step), None)
                for n in nodes:
                    if n.id in steps or (top and n.id == f"step:{top}"):
                        n.on_failure_path = True
                        n.state = "failed" if top and n.id == f"step:{top}" else "warning"
                for e in edges:
                    e.on_failure_path = e.source in steps | {f"step:{top}"} and e.target in steps
            return Graph(nodes=nodes, edges=edges)
        g = self.import_graph()
        keep: set[str] = set(g.nodes)
        if cf:
            from faultsage.analysis.import_graph import module_name

            mods = {i.name for i in cf.impacts if i.kind == "module"}
            tests = {module_name(i.name) for i in cf.impacts if i.kind == "test"}
            root = (
                module_name(cf.hypotheses[0].location.file_path)
                if cf.hypotheses and cf.hypotheses[0].location
                else None
            )
            failing_mods = {module_name(t.split("::")[0]) for t in cf.failing_tests}
            path_nodes = mods | tests | ({root} if root else set()) | failing_mods
            keep = {n for n in path_nodes if n in g}
            if root in g:
                keep |= set(g.predecessors(root)) | set(g.successors(root))
        module_nodes: list[GraphNode] = []
        for mod in sorted(keep)[:300]:
            attrs = g.nodes[mod]
            state: Literal["passed", "failed", "warning", "not_run"] = (
                "failed" if mod in failing_mods else ("warning" if mod in path_nodes else "passed")
            )
            module_nodes.append(
                GraphNode(
                    id=mod,
                    label=mod,
                    kind="test" if attrs.get("is_test") else "module",
                    state=state,
                    on_failure_path=mod in path_nodes,
                )
            )
        ids = {gn.id for gn in module_nodes}
        edges = [
            GraphEdge(
                source=b,
                target=a,
                basis=d.get("basis", "known"),
                on_failure_path=a in path_nodes and b in path_nodes,
            )
            for a, b, d in g.edges(data=True)
            if a in ids and b in ids
        ]
        return Graph(nodes=module_nodes, edges=edges)

    def pipeline(self) -> dict[str, Any]:
        steps = load_pipeline(self.paths)
        cps = repo_events.latest_checkpoints(self.conn, self.project_id)
        return {
            "declared": bool(steps),
            "steps": [
                {
                    "name": s["name"],
                    "inputs": s.get("inputs", []),
                    "outputs": s.get("outputs", []),
                    "checkpoint": cps.get(str(s["name"])),
                }
                for s in steps
            ],
        }

    # ---- writes (gated) ---------------------------------------------------------------------
    def approve(self, suggestion_id: int, via: str, stash_confirmed: bool = False) -> Approval:
        found = repo_incidents.get_suggestion(self.conn, suggestion_id)
        if found is None:
            raise NotFoundError(f"Suggestion S-{suggestion_id} not found.")
        incident_id, sug = found
        patch_sha = sha256_text(sug.patch_diff or "")
        with tx(self.conn):
            approval_id = repo_incidents.create_approval(self.conn, suggestion_id, via, patch_sha)
        try:
            outcome = apply_suggestion(
                self.paths.root,
                self.paths.backups,
                approval_id,
                sug,
                stash_confirmed=stash_confirmed,
            )
        except Exception as e:
            with tx(self.conn):
                approval = repo_incidents.finish_approval(
                    self.conn, approval_id, "refused", getattr(e, "message", str(e)), None
                )
                if getattr(e, "code", "") == "patch_stale":
                    repo_incidents.set_suggestion_state(self.conn, suggestion_id, "stale")
            raise
        with tx(self.conn):
            approval = repo_incidents.finish_approval(
                self.conn, approval_id, outcome.outcome, outcome.detail, outcome.backup_path
            )
            if outcome.outcome == "applied":
                repo_incidents.set_suggestion_state(self.conn, suggestion_id, "applied")
                repo_incidents.set_status(self.conn, incident_id, "fix_applied")
            elif outcome.outcome == "failed_restored":
                repo_incidents.set_suggestion_state(self.conn, suggestion_id, "failed")
        self.emit("incident.updated", {"id": incident_id, "status": self._status_of(incident_id)})
        return approval

    def verify(self, incident_id: int, background: bool = True) -> Verification:
        cf = self.case_file(incident_id)
        if repo_incidents.running_verification(self.conn, incident_id):
            raise VerifyRunningError(
                "A verification is already running for this incident.", "Wait for it to finish."
            )
        node_ids = list(cf.failing_tests)
        for s in cf.suggestions:
            node_ids += [n for n in s.verify_node_ids if n not in node_ids]
        with tx(self.conn):
            vid = repo_incidents.create_verification(self.conn, incident_id)

        def work() -> None:
            try:
                run = run_verify(
                    self.paths.root,
                    node_ids,
                    self.cfg.verify.timeout_seconds,
                    self.cfg.verify.extra_commands,
                )
                with self.lock, tx(self.conn):
                    repo_incidents.finish_verification(self.conn, vid, run.result, run.tests)
                    if run.result == "resolved":
                        repo_incidents.set_status(self.conn, incident_id, "verified")
                    elif cf.status in ("fix_applied", "verified"):
                        repo_incidents.set_status(self.conn, incident_id, "reopened")
            except Exception as e:
                selfmon.record(e, "verify", {"incident": incident_id})
                with tx(self.conn):
                    repo_incidents.finish_verification(self.conn, vid, "error", [])
            self.emit(
                "verification.updated",
                {
                    "id": vid,
                    "incident_id": incident_id,
                    "result": (
                        repo_incidents.get_verification(self.conn, vid)
                        or Verification(
                            id=vid, incident_id=incident_id, started_at=cf.first_seen_at
                        )
                    ).result,
                },
            )

        if background:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()
        v = repo_incidents.get_verification(self.conn, vid)
        if v is None:
            raise NotFoundError(f"Verification V-{vid} not found.")
        return v

    def scan(self) -> int:
        with tx(self.conn):
            sid = repo_events.create_scan(self.conn, self.project_id)
        files = {p: s for p in self.python_files() if (s := self.read_file(p)) is not None}
        installed = _installed_modules()
        ruff = _ruff(self.paths.root)
        findings = run_scan_rules(files, installed, load_pipeline(self.paths), ruff)
        for f in findings:
            if f.get("file_path") and Path(str(f["file_path"])).is_absolute():
                f["file_path"] = to_posix_rel(self.paths.root, str(f["file_path"]))
        with tx(self.conn):
            repo_events.finish_scan(self.conn, sid, findings)
        self.emit("scan.finished", {"id": sid, "findings_count": len(findings)})
        return sid

    def purge(self) -> None:
        with tx(self.conn):
            repo_events.purge(self.conn, self.project_id)
        for p in self.paths.spool.glob("*"):
            if p.is_file():
                p.unlink()
        import shutil

        if self.paths.backups.exists():
            shutil.rmtree(self.paths.backups)
        self.paths.backups.mkdir(parents=True, exist_ok=True)


def _weights_version() -> str:
    from faultsage.analysis.ranker import load_weights

    return load_weights().version


def _installed_modules() -> set[str]:
    mods: set[str] = set(metadata.packages_distributions())
    mods.update(sys.builtin_module_names)
    return mods


def _ruff(root: Path) -> list[dict[str, Any]] | None:
    try:
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--select",
                "F,E999",
                "--output-format",
                "json",
                "--exit-zero",
                "--no-cache",
                ".",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0 or not res.stdout.strip().startswith("["):
        return None
    try:
        data: list[dict[str, Any]] = json.loads(res.stdout)
        return data
    except ValueError:
        return None


def files_digest(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p).encode())
    return h.hexdigest()

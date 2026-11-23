"""Benchmark runner (F14, FR-31 to FR-34, D-023). Writes results/runs/<run_id>/run.json and cases.jsonl.

Per case:
1. Host: check out the buggy and the fixed commit (git worktrees of one mirror per project).
2. Container, network ON: create a venv, install the bug's pinned requirements, run its setup.sh.
3. Container, network OFF: run the developer's failing test command on the buggy and the fixed
   checkout. A case is reproduced only if the buggy run fails and the fixed run passes.
4. Host: parse the buggy run's traceback with FaultSage's own parser, analyse the buggy checkout
   (code + git history), rank files, and compare with the files the developer's fix changed.
   Baselines run on exactly the same inputs.

No FaultSage code runs inside the container, so any Python version and test framework works.
Test files are removed from every method's ranking: the ground truth never contains them.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultsage import __version__
from faultsage.bench.container import InfrastructureError, image_for, run_step
from faultsage.bench.datasets.bugsinpy import Case, is_test_path
from faultsage.bench.metrics import summarise

_mirror_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()
RANDOM_SEEDS = 20


def _git(
    *args: str, cwd: Path | None = None, timeout: int = 900
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def _git_commit() -> str:
    res = _git("rev-parse", "--short", "HEAD", cwd=Path(__file__).parent, timeout=10)
    return res.stdout.strip() or "unknown"


def _mirror(case: Case, work: Path) -> Path | None:
    with _guard:
        lock = _mirror_locks.setdefault(case.project, threading.Lock())
    with lock:
        dest = work / "_mirrors" / case.project
        if not (dest / ".git").exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if _git("clone", "--quiet", case.github_url, str(dest), timeout=1800).returncode != 0:
                return None
        return dest


def _worktree(mirror: Path, commit: str, dest: Path) -> bool:
    if dest.exists():
        return True
    with _mirror_locks[mirror.name]:
        return (
            _git(
                "-C", str(mirror), "worktree", "add", "--detach", "--force", str(dest), commit
            ).returncode
            == 0
        )


def _test_cmd(cmd: str) -> str:
    """Native Python tracebacks from pytest, so the same parser reads every framework."""
    c = cmd.strip()
    if c.startswith(("pytest", "python -m pytest", "py.test")):
        c += " --tb=native -p no:cacheprovider"
    return c


def _run_tests(
    cdir: Path, image: str, which: str, cmds: list[str], timeout: int
) -> tuple[bool, str]:
    outputs: list[str] = []
    ok = True
    for cmd in cmds:
        script = (
            f"export PATH=/case/venv/bin:$PATH PYTHONPATH=/case/{which}; cd /case/{which} && "
            f"{_test_cmd(cmd)}"
        )
        res = run_step(cdir, image, script, network=False, timeout=timeout)
        outputs.append(f"$ {cmd}\n{res.output}")
        ok = ok and res.returncode == 0
    return ok, "\n".join(outputs)


def _rank_files(preds: list[str]) -> list[str]:
    out: list[str] = []
    for p in preds:
        if p and not p.startswith("<") and not is_test_path(p) and p not in out:
            out.append(p)
    return out


def analyse_case(case: Case, buggy_dir: Path, buggy_output: str) -> dict[str, Any]:
    """Run FaultSage and the baselines on a reproduced case. Pure apart from reading the checkout."""
    from faultsage.analysis.engine import GitHunks, Snapshot, analyse
    from faultsage.analysis.traceback_parser import parse_any
    from faultsage.bench.baselines import all_importers_tests, recently_changed, top_frame
    from faultsage.collectors import git_reader
    from faultsage.paths import list_python_files

    prefix = "/case/buggy/"

    def is_project(path: str) -> bool:
        return path.startswith(prefix) and "/case/venv/" not in path

    exc = parse_any(buggy_output, is_project)
    if exc is not None:

        def rel(e: Any) -> Any:
            frames = [
                f.model_copy(update={"file_path": f.file_path[len(prefix) :]})
                if f.is_project
                else f
                for f in e.frames
            ]
            upd: dict[str, Any] = {"frames": frames}
            if e.cause is not None:
                upd["cause"] = rel(e.cause)
            if e.context is not None:
                upd["context"] = rel(e.context)
            return e.model_copy(update=upd)

        exc = rel(exc)

    def read(p: str) -> str | None:
        f = buggy_dir / p
        try:
            return f.read_text(encoding="utf-8", errors="replace") if f.is_file() else None
        except OSError:
            return None

    files = list_python_files(buggy_dir, 20000)
    changes = git_reader.recent_changes(buggy_dir)
    snap = Snapshot(
        read_file=read,
        python_files=files,
        git_changes={p: GitHunks(tuple(c.hunks), c.commit_time) for p, c in changes.items()},
    )
    failing = [t for t in case.test_files if t]
    result = analyse(exc, failing, snap)
    fs_files = _rank_files([h.location.file_path for h in result.hypotheses if h.location])
    tf = _rank_files(top_frame(exc))
    recent = _rank_files(recently_changed({p: c.commit_time for p, c in changes.items()}))
    pool = sorted(set(fs_files) | set(tf) | set(recent[:20]))
    rnd = [_rank_files(random.Random(seed).sample(pool, len(pool))) for seed in range(RANDOM_SEEDS)]
    candidates = [
        {
            "file": h.location.file_path,
            "features": h.features,
            "label": int(h.location.file_path in case.truth_files),
        }
        for h in result.hypotheses
        if h.location and not is_test_path(h.location.file_path)
    ]
    root = case.truth_files[0] if case.truth_files else ""
    return {
        "parsed_exception": exc.type if exc else None,
        "top_certainty": result.hypotheses[0].certainty if result.hypotheses else "unknown",
        "weights_version": result.hypotheses[0].weights_version if result.hypotheses else "",
        "predictions": {
            "faultsage": {"files": fs_files},
            "top_frame": {"files": tf},
            "recent": {"files": recent},
            "random": {"files_by_seed": rnd},
        },
        "candidates": candidates,
        "blast_radius": {
            "predicted_tests": sorted({i.name for i in result.impacts if i.kind == "test"}),
            "actual_failing_tests": sorted(case.test_files),
            "all_importers": sorted(all_importers_tests(result.import_graph, root)) if root else [],
        },
    }


def run_case(
    case: Case, work: Path, timeout: int = 300, install_timeout: int = 1500
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case_id": case.case_id,
        "project": case.project,
        "reproduced": False,
        "python_version": case.python_version,
        "truth": {"files": case.truth_files, "functions": [], "failing_tests": case.test_files},
    }
    if not case.truth_files:
        return {**record, "excluded": "no_non_test_files_in_fix"}
    mirror = _mirror(case, work)
    if mirror is None:
        return {**record, "excluded": "clone_failed"}
    cdir = work / case.case_id
    (cdir / "home").mkdir(parents=True, exist_ok=True)
    if not (
        _worktree(mirror, case.buggy_commit, cdir / "buggy")
        and _worktree(mirror, case.fixed_commit, cdir / "fixed")
    ):
        return {**record, "excluded": "checkout_failed"}
    # Same as BugsInPy's checkout: the bug's test files come from the fixed commit, so the buggy
    # code runs against the test that exposes the bug.
    for tf in case.test_files:
        src, dst = cdir / "fixed" / tf, cdir / "buggy" / tf
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    (cdir / "requirements.txt").write_text(case.requirements, encoding="utf-8")
    (cdir / "setup.sh").write_text(case.setup, encoding="utf-8")
    pipcache = work / "_pipcache"
    pipcache.mkdir(exist_ok=True)
    for d in (cdir, pipcache):
        subprocess.run(["chown", "-R", "1000:1000", str(d)], check=False, capture_output=True)
    image = image_for(case.python_version)
    install = (
        "set -e; python -m venv /case/venv; . /case/venv/bin/activate; "
        "export PIP_CACHE_DIR=/pipcache; "
        "if [ -s /case/requirements.txt ]; then pip install -q -r /case/requirements.txt; fi; "
        "pip install -q pytest >/dev/null 2>&1 || true; "
        "export SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0; "
        # Install each checkout itself (generated version files, entry points), then its setup.sh.
        "for d in buggy fixed; do (cd /case/$d && "
        "(pip install -q --no-deps --no-build-isolation -e . >/dev/null 2>&1 || true) && bash /case/setup.sh); done"
    )
    if not (cdir / "venv" / ".installed").exists():
        res = run_step(
            cdir,
            image,
            install + "; touch /case/venv/.installed",
            network=True,
            timeout=install_timeout,
            cpus="2",
            extra_mounts=[(pipcache, "/pipcache")],
        )
        if res.returncode != 0:
            return {**record, "excluded": "dependency_install_failed", "log": res.output[-3000:]}
    buggy_ok, buggy_out = _run_tests(cdir, image, "buggy", case.test_commands, timeout)
    if buggy_ok:
        return {**record, "excluded": "test_not_failing_on_buggy", "log": buggy_out[-3000:]}
    fixed_ok, fixed_out = _run_tests(cdir, image, "fixed", case.test_commands, timeout)
    if not fixed_ok:
        return {**record, "excluded": "fixed_version_still_fails", "log": fixed_out[-3000:]}
    # Hand the checkout back to this user so git reads its history without trusting other owners.
    subprocess.run(
        ["chown", "-R", f"{os.getuid()}:{os.getgid()}", str(cdir / "buggy")],
        check=False,
        capture_output=True,
    )
    (cdir / "buggy.log").write_text(buggy_out, encoding="utf-8")
    record.update({"reproduced": True, "verify": {"buggy": "still_failing", "fixed": "resolved"}})
    record.update(analyse_case(case, cdir / "buggy", buggy_out))
    return record


def run_cases(
    cases: list[Case], work: Path, workers: int = 3, log: Any = print
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for rec in pool.map(lambda c: _safe(c, work), cases):
            out.append(rec)
            hit = rec.get("predictions", {}).get("faultsage", {}).get("files", [])[:3]
            log(
                f"{rec['case_id']}: reproduced={rec['reproduced']} {rec.get('excluded', '')}"
                + (
                    f" top3_hit={any(f in rec['truth']['files'] for f in hit)}"
                    if rec["reproduced"]
                    else ""
                )
            )
    return out


def _safe(case: Case, work: Path) -> dict[str, Any]:
    try:
        return run_case(case, work)
    except InfrastructureError:
        raise
    except Exception as e:
        return {
            "case_id": case.case_id,
            "project": case.project,
            "reproduced": False,
            "excluded": f"harness_error:{type(e).__name__}",
            "truth": {"files": case.truth_files},
        }


def write_run(
    run_dir: Path,
    dataset: str,
    dataset_version: str,
    split: str,
    split_file: str,
    cases: list[dict[str, Any]],
    started: datetime,
    projects: list[str],
    seed: int = 7,
    extra: dict[str, Any] | None = None,
) -> Path:
    from faultsage.analysis.engine import NAME as ENGINE_NAME
    from faultsage.analysis.ranker import load_weights, weights_file

    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "cases.jsonl").open("w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(
                json.dumps(
                    {
                        **{k: v for k, v in c.items() if k != "log"},
                        **({"log_tail": c["log"][-1500:]} if c.get("log") else {}),
                    }
                )
                + "\n"
            )
    excluded = Counter(str(c.get("excluded")) for c in cases if not c.get("reproduced"))
    metrics = summarise(cases)
    run = {
        "run_id": run_dir.name,
        "faultsage_commit": _git_commit(),
        "faultsage_version": __version__,
        "dataset": dataset,
        "dataset_version": dataset_version,
        "split": split,
        "split_file": split_file,
        "projects_run": projects,
        "level": "file",
        "seed": seed,
        "cases_attempted": len(cases),
        "cases_reproduced": sum(1 for c in cases if c.get("reproduced")),
        "cases_excluded": dict(excluded),
        "metrics": {
            "faultsage": metrics["methods"].get("faultsage", {}),
            **{k: v for k, v in metrics.items() if k not in ("methods", "n")},
        },
        "baselines": {m: v for m, v in metrics["methods"].items() if m != "faultsage"},
        "weights_version": load_weights().version,
        "weights_file_sha256": hashlib.sha256(weights_file().read_bytes()).hexdigest(),
        "engine": ENGINE_NAME,
        "machine": {"cpus": os.cpu_count()},
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        **(extra or {}),
    }
    (run_dir / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    return run_dir / "run.json"


def cleanup(work: Path) -> None:
    """Remove checkouts and venvs of a finished run (benchmark scratch data only)."""
    shutil.rmtree(work, ignore_errors=True)

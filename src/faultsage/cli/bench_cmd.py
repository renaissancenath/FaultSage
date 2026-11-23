"""faultsage bench fetch|run|report (FR-31 to FR-34). Runs inside WSL2 Ubuntu with Docker Engine."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import typer

bench_app = typer.Typer(help="Benchmarks on real bugs (BugsInPy).", no_args_is_help=True)
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "data"
SPLITS = Path(__file__).resolve().parents[1] / "bench" / "splits"


@bench_app.command("fetch")
def fetch(dataset: str = typer.Argument("bugsinpy")) -> None:
    """Download a dataset from its official source and print the version recorded."""
    if dataset != "bugsinpy":
        typer.echo(
            f"{dataset}: adapter not built yet (stage 8). Only bugsinpy is available.", err=True
        )
        raise typer.Exit(2)
    from faultsage.bench.datasets.bugsinpy import fetch as do_fetch

    DATA.mkdir(exist_ok=True)
    typer.echo(f"Fetched BugsInPy at {do_fetch(DATA)}")


@bench_app.command("run")
def run(
    dataset: str = typer.Argument("bugsinpy"),
    split: str = typer.Option("dev", "--split"),
    projects: list[str] = typer.Option(None, "--projects"),
    limit: int = typer.Option(
        0, "--limit", help="Only the first N cases per project (smoke runs)."
    ),
    workers: int = typer.Option(3, "--workers", help="Cases run in parallel."),
) -> None:
    """Run FaultSage and baselines on real cases and write a run record."""
    from faultsage.bench.container import engine
    from faultsage.bench.datasets.bugsinpy import fetch as do_fetch
    from faultsage.bench.datasets.bugsinpy import load_cases
    from faultsage.bench.runner import run_cases, write_run

    if engine() is None:
        typer.echo(
            "No container engine. Benchmarks run only in Docker Engine or Podman (SR-24).", err=True
        )
        raise typer.Exit(2)
    split_file = SPLITS / "bugsinpy_v1.json"
    split_projects = json.loads(split_file.read_text(encoding="utf-8"))[split]
    chosen = [p for p in (projects or split_projects) if p in split_projects]
    if projects and len(chosen) != len(projects):
        typer.echo(
            f"Refusing: {sorted(set(projects) - set(chosen))} are not in the {split} split.",
            err=True,
        )
        raise typer.Exit(2)
    version = do_fetch(DATA)
    cases = []
    for proj in chosen:
        pc = load_cases(DATA, [proj])
        cases += pc[:limit] if limit else pc
    started = datetime.now(UTC)
    typer.echo(f"{len(cases)} cases from {', '.join(chosen)} ({split} split)")
    records = run_cases(cases, DATA / "work", workers=workers, log=typer.echo)
    run_id = f"{started:%Y-%m-%d}_{dataset}_{split}_{started:%H%M%S}"
    out = write_run(
        REPO_ROOT / "results" / "runs" / run_id,
        dataset,
        version,
        split,
        str(split_file.relative_to(REPO_ROOT)),
        records,
        started,
        chosen,
    )
    typer.echo(f"Run record: {out}")


@bench_app.command("reanalyse")
def reanalyse(
    run_id: str = typer.Argument(..., help="Run whose saved test logs are analysed again."),
) -> None:
    """Re-run only the host-side analysis on a run's saved logs (no containers), as a NEW run record.

    Used while developing features on the dev split. The original record is kept unchanged.
    """
    from faultsage.bench.datasets.bugsinpy import load_cases
    from faultsage.bench.records import get_run
    from faultsage.bench.runner import analyse_case, write_run

    run = get_run(run_id)
    if run is None:
        typer.echo(f"No run {run_id}.", err=True)
        raise typer.Exit(1)
    by_id = {c.case_id: c for c in load_cases(DATA, run.get("projects_run") or None)}
    started = datetime.now(UTC)
    records = []
    for rec in run["cases"]:
        log = DATA / "work" / rec["case_id"] / "buggy.log"
        if rec.get("reproduced") and rec["case_id"] in by_id and log.exists():
            case = by_id[rec["case_id"]]
            rec = {
                **rec,
                **analyse_case(
                    case, DATA / "work" / rec["case_id"] / "buggy", log.read_text(encoding="utf-8")
                ),
            }
        records.append(rec)
    new_id = f"{started:%Y-%m-%d}_{run['dataset']}_{run['split']}_{started:%H%M%S}_reanalysed"
    out = write_run(
        REPO_ROOT / "results" / "runs" / new_id,
        run["dataset"],
        run["dataset_version"],
        run["split"],
        run["split_file"],
        records,
        started,
        run.get("projects_run", []),
        extra={"reanalysed_from": run_id},
    )
    typer.echo(f"Run record: {out}")


@bench_app.command("train")
def train(
    run_id: str = typer.Argument(..., help="A dev-split run id to learn the ranking weights from."),
) -> None:
    """Fit the ranker weights on a DEV run (needs the faultsage_engine package)."""
    from faultsage.bench.records import get_run

    try:
        from faultsage_engine.training import fit_weights
    except ModuleNotFoundError as e:
        typer.echo(
            "Training is part of the ranking engine package, which is not installed.", err=True
        )
        raise typer.Exit(1) from e

    run = get_run(run_id)
    if run is None:
        typer.echo(f"No run {run_id}.", err=True)
        raise typer.Exit(1)
    if run.get("split") != "dev":
        typer.echo("Refusing: weights are trained on the dev split only (D-007).", err=True)
        raise typer.Exit(2)
    summary = fit_weights(run)
    typer.echo(json.dumps(summary, indent=2))


@bench_app.command("report")
def report(run_id: str) -> None:
    """Print a run's metrics with baselines side by side."""
    from faultsage.bench.records import get_run

    run = get_run(run_id)
    if run is None:
        typer.echo(f"No run {run_id} in results/runs.", err=True)
        raise typer.Exit(1)
    typer.echo(f"{run['run_id']}  {run['dataset']} {run['dataset_version']}  split={run['split']}")
    typer.echo(
        f"Attempted {run['cases_attempted']}, reproduced {run['cases_reproduced']}, excluded {run['cases_excluded']}"
    )
    rows = {"faultsage": run["metrics"].get("faultsage", {}), **run.get("baselines", {})}
    typer.echo(f"{'method':<12} {'top1':>6} {'top3':>6} {'top5':>6}")
    for m, v in rows.items():
        typer.echo(
            f"{m:<12} "
            + " ".join(f"{v.get(k, {}).get('mean', 0):>6.3f}" for k in ("top1", "top3", "top5"))
        )

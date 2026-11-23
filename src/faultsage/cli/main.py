"""FaultSage CLI (TRD section 5.1)."""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
import time
import webbrowser
from pathlib import Path

import typer

from faultsage import __version__
from faultsage.cli.bench_cmd import bench_app
from faultsage.cli.cloud_cmd import cloud_app
from faultsage.cli.db_cmd import db_app
from faultsage.config import loader
from faultsage.config.model import Config, ProjectCfg
from faultsage.errors import FaultSageError
from faultsage.selfmon import hook as selfmon

app = typer.Typer(
    help="FaultSage: finds the line that broke your Python project and checks your fix.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(db_app, name="db")
app.add_typer(bench_app, name="bench")
app.add_typer(cloud_app, name="cloud")


def _fail(exc: FaultSageError) -> None:
    typer.echo(f"Error: {exc.message}", err=True)
    if exc.next_step:
        typer.echo(f"Next: {exc.next_step}", err=True)
    raise typer.Exit(1)


def _paths(path: Path | None = None) -> loader.ProjectPaths:
    try:
        return loader.locate(path)
    except FaultSageError as e:
        _fail(e)
        raise


def _workspace(paths: loader.ProjectPaths):  # type: ignore[no-untyped-def]
    from faultsage.daemon.service import Workspace

    try:
        return Workspace.open(paths)
    except FaultSageError as e:
        _fail(e)


@app.callback(invoke_without_command=True)
def _main(
    version: bool = typer.Option(False, "--version", help="Show the version and exit."),
) -> None:
    selfmon.install("cli")
    if version:
        typer.echo(f"faultsage {__version__}")
        raise typer.Exit()


@app.command()
def init(
    path: Path = typer.Argument(None, help="Project folder (default: current folder)."),
    force: bool = typer.Option(False, "--force", help="Replace an existing config (backup kept)."),
    yes: bool = typer.Option(False, "--yes", help="Answer yes to the .gitignore question."),
) -> None:
    """Detect the project and write .faultsage/config.toml (FR-1 to FR-4)."""
    from faultsage.collectors import git_reader
    from faultsage.paths import find_project_root

    start = (path or Path.cwd()).resolve()
    root = find_project_root(start)
    if root is None:
        typer.echo(
            "No pyproject.toml, setup.py, requirements file or .git found. Pass a path.", err=True
        )
        raise typer.Exit(1)
    paths = loader.ProjectPaths(root)
    from faultsage.paths import list_python_files

    py_files = list_python_files(root)
    tests = [
        p for p in py_files if p.rsplit("/", 1)[-1].startswith("test_") or p.endswith("_test.py")
    ]
    sources = sorted({p.split("/")[0] for p in py_files if p not in tests and "/" in p})
    deps = [
        p.name
        for p in [root / "pyproject.toml", root / "setup.py", *root.glob("requirements*.txt")]
        if p.exists()
    ]
    head, branch = git_reader.head(root)
    typer.echo(f"Project: {root.name} ({root})")
    typer.echo(
        f"Sources: {', '.join(sources) or 'top-level files'} ({len(py_files) - len(tests)} files)"
    )
    typer.echo(f"Tests:   {len(tests)} test files")
    typer.echo(f"Deps:    {', '.join(deps) or 'none found'}")
    typer.echo(f"Git:     {f'{branch} @ {head}' if head else 'not a git repository'}")
    typer.echo(
        "Pipeline: "
        + (
            "declared"
            if paths.pipeline.exists()
            else "not declared (add .faultsage/pipeline.toml to map steps)"
        )
    )
    cfg = Config(project=ProjectCfg(name=root.name), signals={"git": head is not None})  # type: ignore[arg-type]
    try:
        backup = loader.save(paths, cfg, force=force)
    except FaultSageError as e:
        _fail(e)
        return
    if backup:
        typer.echo(f"Backup:  {backup}")
    typer.echo(f"Config written: {paths.config}")
    gi = root / ".gitignore"
    line = ".faultsage/"
    already = gi.exists() and line in gi.read_text(encoding="utf-8").splitlines()
    if not already and (
        yes or typer.confirm("Add .faultsage/ data folder to .gitignore?", default=True)
    ):
        with gi.open("a", encoding="utf-8") as fh:
            fh.write(
                ("\n" if gi.exists() and not gi.read_text(encoding="utf-8").endswith("\n") else "")
                + line
                + "\n"
            )
        typer.echo("Added .faultsage/ to .gitignore")
    typer.echo("Next: faultsage watch")


def _free_port(start: int) -> int:
    for port in range(start, start + 11):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise typer.BadParameter(f"Ports {start} to {start + 10} are all in use. Pass --port.")


@app.command()
def watch(
    port: int = typer.Option(None, "--port", help="Dashboard port (default from config)."),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the dashboard in a browser."
    ),
    approve: list[int] = typer.Option([], "--approve-migration", hidden=True),
) -> None:
    """Start the daemon and the local dashboard."""
    import threading

    import uvicorn

    from faultsage.api.app import create_app
    from faultsage.api.auth import SessionStore
    from faultsage.daemon.runner import Daemon, DaemonLockedError
    from faultsage.daemon.service import Workspace

    paths = _paths()
    try:
        ws = Workspace.open(paths, set(approve))
    except FaultSageError as e:
        _fail(e)
        return
    chosen = _free_port(port or ws.cfg.dashboard.port)
    sessions = SessionStore()
    daemon = Daemon(ws, chosen)
    try:
        daemon.start()
    except DaemonLockedError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e
    token = sessions.new_token()
    _write_session(paths, token, chosen)
    server: uvicorn.Server | None = None

    def stop_server() -> None:
        if server is not None:
            server.should_exit = True

    daemon.on_stop.append(stop_server)
    daemon.on_stop.append(sessions.revoke_all)
    api = create_app(
        ws, sessions, chosen, on_stop=lambda: threading.Timer(0.2, daemon.stop).start()
    )
    # SR-1: host is fixed to loopback; config validation already refuses anything else.
    server = uvicorn.Server(
        uvicorn.Config(
            api,
            host="127.0.0.1",
            port=chosen,
            log_level="warning",
            access_log=False,
            server_header=False,
        )
    )

    def token_requests() -> None:
        while not daemon._stop.is_set():
            req = paths.data / "token-request"
            if req.exists():
                with contextlib.suppress(OSError):
                    req.unlink()
                _write_session(paths, sessions.new_token(), chosen)
            time.sleep(0.2)

    threading.Thread(target=token_requests, daemon=True).start()
    url = f"http://127.0.0.1:{chosen}/#t={token}"
    sig = ws.cfg.signals
    on = [
        n
        for n, v in (
            ("pytest", sig.pytest),
            ("run wrapper", sig.run_wrapper),
            ("git", sig.git),
            ("file saves", sig.file_watch),
            ("logs", bool(sig.logs)),
        )
        if v
    ]
    typer.echo(f"Watching {ws.cfg.project.name}. Signals on: {', '.join(on)}.")
    typer.echo(f"Dashboard: {url}")
    typer.echo("Stop with Ctrl+C or faultsage stop.")
    if open_browser and not os.environ.get("CI"):
        with contextlib.suppress(Exception):
            webbrowser.open(url)
    try:
        server.run()
    finally:
        daemon.stop()


def _write_session(paths: loader.ProjectPaths, token: str, port: int) -> None:
    paths.session.write_text(json.dumps({"token": token, "port": port}), encoding="utf-8")
    with contextlib.suppress(OSError):
        paths.session.chmod(0o600)


def _control(cmd: str) -> None:
    from faultsage.daemon.runner import send_control

    paths = _paths()
    if not send_control(paths, cmd):
        typer.echo(
            "No FaultSage daemon is running for this project. Start one with faultsage watch."
        )
        raise typer.Exit(1)
    typer.echo(
        {
            "pause": "Paused. New signals are queued and will be processed when you resume.",
            "resume": "Resumed.",
            "stop": "Stopping the daemon.",
        }[cmd]
    )


@app.command()
def pause() -> None:
    """Pause ingest. Collectors still write to the spool."""
    _control("pause")


@app.command()
def resume() -> None:
    """Resume ingest."""
    _control("resume")


@app.command()
def stop() -> None:
    """Stop the daemon and revoke dashboard sessions."""
    _control("stop")


@app.command()
def logout() -> None:
    """Revoke all dashboard sessions (LR-6)."""
    _control("stop")


@app.command()
def status() -> None:
    """Show daemon state and open incidents."""
    from faultsage.daemon.runner import read_lock

    paths = _paths()
    lock = read_lock(paths)
    ws = _workspace(paths)
    st = ws.status()
    if lock:
        typer.echo(
            f"Daemon: {lock.get('state', 'running')} (PID {lock['pid']}, port {lock['port']})"
        )
    else:
        typer.echo("Daemon: stopped")
    typer.echo(f"Project: {st['project']} ({st['root']})")
    typer.echo(f"Open incidents: {st['open_incidents']}")


@app.command()
def scan() -> None:
    """One-off deep scan: imports, dependencies, cycles, undefined names, pipeline."""
    paths = _paths()
    ws = _workspace(paths)
    from faultsage.storage.repo_events import get_scan

    sid = ws.scan()
    result = get_scan(ws.conn, sid) or {"findings": []}
    if not result["findings"]:
        typer.echo("Scan finished: no findings.")
    for f in result["findings"]:
        where = f"{f['file_path']}:{f['line']}" if f.get("line") else (f.get("file_path") or "")
        typer.echo(f"{f['severity']:<8} {f['rule']:<20} {where}  {f['message']}")
    typer.echo(f"\n{len(result['findings'])} finding(s)")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(ctx: typer.Context) -> None:
    """Run a command and record failures: faultsage run -- python -m mypipeline"""
    from faultsage.collectors.run_wrapper import run_and_record

    argv = list(ctx.args)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        typer.echo("Usage: faultsage run -- COMMAND [ARGS...]", err=True)
        raise typer.Exit(2)
    paths = _paths()
    try:
        loader.load(paths)
    except FaultSageError as e:
        _fail(e)
    raise typer.Exit(run_and_record(paths, argv))


def _ingest_now(ws) -> None:  # type: ignore[no-untyped-def]
    from faultsage.daemon.runner import read_lock

    if read_lock(ws.paths) is None:  # no daemon: ingest synchronously so the CLI is current
        ws.ingest()


@app.command()
def incidents(open_only: bool = typer.Option(False, "--open", help="Only open incidents.")) -> None:
    """List incidents."""
    ws = _workspace(_paths())
    _ingest_now(ws)
    items, _ = ws.list_incidents("open_any" if open_only else None, None, 200, None)
    if not items:
        typer.echo("No incidents yet. Run pytest while faultsage watch is running.")
        return
    for i in items:
        typer.echo(
            f"I-{i.id:<5} {i.status:<13} {(i.top_certainty or '-'):<9} x{i.occurrence_count:<4} {i.title}"
        )


@app.command()
def show(incident: str = typer.Argument(..., help="Incident id, for example I-3 or 3.")) -> None:
    """Print a case file."""
    from faultsage.export import to_markdown

    ws = _workspace(_paths())
    _ingest_now(ws)
    try:
        cf = ws.case_file(_id(incident))
    except FaultSageError as e:
        _fail(e)
        return
    typer.echo(to_markdown(cf, ws.cfg.project.name))


def _id(value: str) -> int:
    v = value.strip().upper()
    for prefix in ("I-", "S-", "V-", "A-"):
        v = v.removeprefix(prefix)
    if not v.isdigit():
        raise typer.BadParameter(f"{value} is not an id like I-3.")
    return int(v)


@app.command()
def apply(
    suggestion: str = typer.Argument(..., help="Suggestion id, for example S-17."),
    stash_confirmed: bool = typer.Option(
        False, "--stash-confirmed", help="You stashed your changes yourself."
    ),
) -> None:
    """Apply a patch after typed confirmation (F10). Creates a backup and an approvals record."""
    from faultsage.storage import repo_incidents

    ws = _workspace(_paths())
    sid = _id(suggestion)
    found = repo_incidents.get_suggestion(ws.conn, sid)
    if found is None or not found[1].patch_diff:
        typer.echo(f"S-{sid} not found or has no patch.", err=True)
        raise typer.Exit(1)
    typer.echo(found[1].patch_diff)
    typer.echo(f"Files: {', '.join(found[1].files)}")
    typed = typer.prompt(f"Type 'apply S-{sid}' to apply this patch")
    if typed.strip() != f"apply S-{sid}":
        typer.echo("Not applied. Nothing changed.")
        raise typer.Exit(1)
    try:
        approval = ws.approve(sid, "cli", stash_confirmed)
    except FaultSageError as e:
        _fail(e)
        return
    typer.echo(f"A-{approval.id}: {approval.outcome}. {approval.outcome_detail or ''}")
    if approval.backup_path:
        typer.echo(f"Backup: {approval.backup_path}")
    if approval.outcome == "applied":
        typer.echo(f"Next: faultsage verify I-{found[0]}")


@app.command()
def verify(incident: str = typer.Argument(..., help="Incident id, for example I-42.")) -> None:
    """Rerun the failing and affected tests and report the result."""
    from faultsage.storage import repo_incidents

    ws = _workspace(_paths())
    _ingest_now(ws)
    iid = _id(incident)
    try:
        v = ws.verify(iid, background=False)
    except FaultSageError as e:
        _fail(e)
        return
    v = repo_incidents.get_verification(ws.conn, v.id) or v
    passed = sum(t.outcome == "passed" for t in v.tests)
    words = {
        "resolved": "Fixed",
        "still_failing": "Still failing",
        "new_failures": "New failures",
        "timeout": "Timed out",
        "error": "Could not run",
    }
    typer.echo(f"{words.get(v.result or '', v.result)}: {passed} of {len(v.tests)} tests pass.")
    for t in v.tests:
        typer.echo(f"  {t.outcome:<7} {t.node_id}")
    raise typer.Exit(0 if v.result == "resolved" else 1)


@app.command()
def dashboard() -> None:
    """Open the dashboard of the running daemon with a fresh one-time link."""
    from faultsage.daemon.runner import read_lock

    paths = _paths()
    if read_lock(paths) is None:
        typer.echo("No FaultSage daemon is running. Start one with faultsage watch.")
        raise typer.Exit(1)
    before = paths.session.stat().st_mtime if paths.session.exists() else 0
    (paths.data / "token-request").write_text("1", encoding="utf-8")
    for _ in range(50):
        if paths.session.exists() and paths.session.stat().st_mtime > before:
            break
        time.sleep(0.1)
    data = json.loads(paths.session.read_text(encoding="utf-8"))
    url = f"http://127.0.0.1:{data['port']}/#t={data['token']}"
    typer.echo(f"Dashboard: {url}")
    with contextlib.suppress(Exception):
        webbrowser.open(url)


@app.command()
def export(
    incident: str,
    format: str = typer.Option("md", "--format", help="md or json"),
    output: Path = typer.Option(None, "--output", "-o", help="File to write (default: stdout)."),
) -> None:
    """Export a case file as Markdown or JSON (redacted)."""
    from faultsage.export import to_markdown

    ws = _workspace(_paths())
    _ingest_now(ws)
    cf = ws.case_file(_id(incident))
    text = (
        cf.model_dump_json(indent=2) if format == "json" else to_markdown(cf, ws.cfg.project.name)
    )
    if output:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"Written: {output}")
    else:
        typer.echo(text)


@app.command()
def purge(
    all_: bool = typer.Option(
        False, "--all", help="Also delete config and the whole .faultsage folder."
    ),
) -> None:
    """Delete local FaultSage data after typed confirmation (SR-27)."""
    import shutil

    paths = _paths()
    cfg = loader.load(paths)
    sizes = sum(f.stat().st_size for f in paths.data.rglob("*") if f.is_file())
    what = (
        "the whole .faultsage folder (config, database, backups, spool, logs)"
        if all_
        else "events, incidents, backups and spool (config and approvals audit kept)"
    )
    typer.echo(f"This deletes {what}: {sizes / 1024:.0f} KB.")
    typed = typer.prompt(f"Type 'purge {cfg.project.name}' to confirm")
    if typed.strip() != f"purge {cfg.project.name}":
        typer.echo("Nothing was deleted.")
        raise typer.Exit(1)
    from faultsage.daemon.runner import read_lock

    if read_lock(paths):
        typer.echo("Stop the daemon first: faultsage stop", err=True)
        raise typer.Exit(1)
    if all_:
        shutil.rmtree(paths.data)
        typer.echo("Deleted .faultsage/")
        return
    ws = _workspace(paths)
    ws.purge()
    typer.echo("Purged.")


@app.command("self-report")
def self_report(
    export_: bool = typer.Option(
        False, "--export", help="Write a redacted report file to attach to an issue."
    ),
) -> None:
    """Show FaultSage's own recent errors (self-monitoring)."""
    groups = selfmon.grouped()
    if not groups:
        typer.echo("No internal errors recorded.")
        return
    for g in groups:
        typer.echo(
            f"{g['fingerprint']}  x{g['count']:<4} {g['type']}: {g['message'][:80]}  (last {g['last']}, in {g['where']})"
        )
    if export_:
        out = Path.cwd() / f"faultsage-self-report-{int(time.time())}.json"
        out.write_text(
            json.dumps(
                {"version": __version__, "python": sys.version.split()[0], "groups": groups},
                indent=2,
            ),
            encoding="utf-8",
        )
        typer.echo(
            f"Written: {out}. Check it for anything private before attaching it to an issue."
        )


@app.command()
def triage(
    report: Path = typer.Argument(..., help="A self-report export or incident JSON export."),
) -> None:
    """Triage a production-only bug report: group, locate, and draft a failing test (PROMPTS.md)."""
    from faultsage.triage import triage_report

    typer.echo(triage_report(json.loads(report.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    app()

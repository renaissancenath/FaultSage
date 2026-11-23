"""faultsage-cloud: run the hosted service and manage its database (operator commands)."""

from __future__ import annotations

import os
from pathlib import Path

import typer

app = typer.Typer(
    help="FaultSage Cloud server and database commands.", no_args_is_help=True, add_completion=False
)
db_app = typer.Typer(help="Cloud database migrations.", no_args_is_help=True)
app.add_typer(db_app, name="db")


@app.command()
def serve(
    host: str = typer.Option(
        None, help="Bind address (default 0.0.0.0 in a container, else 127.0.0.1)."
    ),
    port: int = typer.Option(None, help="Port (default $PORT or 8000)."),
) -> None:
    """Run the web server."""
    import uvicorn

    from faultsage.cloud.app import create_app

    # The hosted service is meant to be reachable, unlike the local dashboard (SR-1 applies to local).
    bind = host or os.environ.get("FAULTSAGE_BIND", "127.0.0.1")
    uvicorn.run(
        create_app(),
        host=bind,
        port=port or int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        server_header=False,
        access_log=False,
    )


@db_app.command("status")
def status() -> None:
    """List pending cloud migrations."""
    from faultsage.cloud.storage.db import pending

    todo = pending()
    if not todo:
        typer.echo("Cloud database is up to date.")
    for m in todo:
        typer.echo(
            f"{m.version:04d} {m.name}  {'DESTRUCTIVE: needs approval' if m.destructive else 'safe'}"
        )


@db_app.command("migrate")
def migrate_cmd(
    approve: int = typer.Option(
        None, "--approve", help="Approve ONE destructive migration for this run."
    ),
    env: str = typer.Option(
        ..., "--env", help="Environment you are migrating: development, staging, production."
    ),
    approved_by: str = typer.Option("", "--approved-by", help="Name of the person approving."),
    backup_dir: Path = typer.Option(Path("backups"), "--backup-dir"),
    backup_ref: str = typer.Option(
        None, "--backup-ref", help="Use an existing provider snapshot id instead of pg_dump."
    ),
) -> None:
    """Apply migrations. Destructive ones need --approve, --approved-by, typed confirmation and a backup.
    Approval covers one migration, one environment, one run. It never carries over."""
    from faultsage.cloud.settings import database_url_from_env, environment_from_env
    from faultsage.cloud.storage.db import migrate, pending
    from faultsage.errors import FaultSageError
    from faultsage.migration_gate import describe

    current_env = environment_from_env()
    where = database_url_from_env().split("@")[-1]
    if env != current_env:
        typer.echo(f"--env {env} does not match FAULTSAGE_ENV={current_env}. Refusing.", err=True)
        raise typer.Exit(1)
    approved: set[int] = set()
    if approve is not None:
        target = next((m for m in pending() if m.version == approve), None)
        if target is None:
            typer.echo(f"{approve:04d} is not pending.", err=True)
            raise typer.Exit(1)
        if target.destructive:
            typer.echo(describe(target))
            typer.echo(f"Environment: {env}. Database: {where}")
            typed = typer.prompt(f"Type 'approve {approve:04d} on {env}' to run it now")
            if typed.strip() != f"approve {approve:04d} on {env}":
                typer.echo("Not approved. Nothing ran.")
                raise typer.Exit(1)
        approved.add(approve)
    try:
        done = migrate(
            approve=approved,
            environment=env,
            approved_by=approved_by,
            backup_dir=backup_dir,
            backup_ref=backup_ref,
        )
    except FaultSageError as e:
        typer.echo(e.message, err=True)
        typer.echo(
            f"Next: faultsage-cloud {e.next_step}"
            if e.next_step.startswith("db ")
            else f"Next: {e.next_step}",
            err=True,
        )
        raise typer.Exit(1) from e
    for m, ref in done:
        typer.echo(f"Applied {m.version:04d} {m.name}" + (f" (backup: {ref})" if ref else ""))
    if not done:
        typer.echo("Nothing to apply.")


@db_app.command("backup")
def backup_cmd(
    out_dir: Path = typer.Option(Path("backups"), "--out-dir", help="Folder for the backup file."),
) -> None:
    """Take a full backup of the cloud database now (pg_dump custom format, or a SQLite copy).
    Backups contain customer data: keep them private and encrypted, never in the git repository."""
    from faultsage.cloud.storage.db import dump, engine
    from faultsage.errors import FaultSageError

    try:
        path = dump(engine(), out_dir, "manual")
    except FaultSageError as e:
        typer.echo(f"{e.message}\nNext: {e.next_step}", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"Backup written: {path}")


@db_app.command("restore")
def restore_cmd(
    dump_file: Path = typer.Argument(..., help="Backup made by 'faultsage-cloud db backup'."),
    env: str = typer.Option(..., "--env", help="Environment you are restoring."),
    approved_by: str = typer.Option("", "--approved-by", help="Name of the person approving."),
    backup_dir: Path = typer.Option(Path("backups"), "--backup-dir"),
) -> None:
    """Replace ALL data in the cloud database with a backup. Destructive: asks you to type a
    confirmation every time, backs up the current data first, and records who approved it."""
    from faultsage.cloud.settings import database_url_from_env, environment_from_env
    from faultsage.cloud.storage.db import engine, restore
    from faultsage.errors import FaultSageError

    current_env = environment_from_env()
    where = database_url_from_env().split("@")[-1]
    if env != current_env:
        typer.echo(f"--env {env} does not match FAULTSAGE_ENV={current_env}. Refusing.", err=True)
        raise typer.Exit(1)
    typer.echo(
        f"This replaces every account, project and event in {where} "
        f"({env}) with the contents of {dump_file.name}. Changes since that backup are lost."
    )
    phrase = f"restore {dump_file.name} on {env}"
    if typer.prompt(f"Type '{phrase}' to continue").strip() != phrase:
        typer.echo("Not approved. Nothing changed.")
        raise typer.Exit(1)
    try:
        safety = restore(
            engine(), dump_file, environment=env, approved_by=approved_by, backup_dir=backup_dir
        )
    except FaultSageError as e:
        typer.echo(f"{e.message}\nNext: {e.next_step}", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"Restored from {dump_file}. The data from before the restore is in {safety}.")


if __name__ == "__main__":
    app()

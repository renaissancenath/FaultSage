"""faultsage db: migration status and the destructive-migration gate (DATABASE.md 4, SR-26)."""

from __future__ import annotations

import typer

from faultsage.config import loader
from faultsage.errors import FaultSageError
from faultsage.migration_gate import describe
from faultsage.storage.db import connect, migrate, pending

db_app = typer.Typer(help="Database migrations.", no_args_is_help=True)


@db_app.command("status")
def status() -> None:
    """List pending migrations and whether each is destructive."""
    paths = loader.locate()
    conn = connect(paths.db)
    try:
        todo = pending(conn)
    except FaultSageError as e:
        typer.echo(f"Error: {e.message}", err=True)
        raise typer.Exit(1) from e
    if not todo:
        typer.echo("Database is up to date.")
    for m in todo:
        typer.echo(
            f"{m.version:04d} {m.name}  {'DESTRUCTIVE, needs --approve' if m.destructive else 'safe, applied on start'}"
        )


@db_app.command("migrate")
def migrate_cmd(
    approve: int = typer.Option(
        None, "--approve", help="Approve ONE destructive migration version for this run only."
    ),
) -> None:
    """Apply pending migrations. Destructive ones need --approve VERSION and typed confirmation."""
    paths = loader.locate()
    conn = connect(paths.db)
    approved: set[int] = set()
    if approve is not None:
        target = next((m for m in pending(conn) if m.version == approve), None)
        if target is None:
            typer.echo(f"Migration {approve:04d} is not pending.", err=True)
            raise typer.Exit(1)
        if target.destructive:
            typer.echo(describe(target))
            typer.echo(f"Database: {paths.db}")
            typed = typer.prompt(
                f"Type 'approve {approve:04d}' to run it now (a backup is written first)"
            )
            if typed.strip() != f"approve {approve:04d}":
                typer.echo("Not approved. Nothing ran.")
                raise typer.Exit(1)
        approved.add(approve)
    try:
        done = migrate(conn, paths.db, approved)
    except FaultSageError as e:
        typer.echo(e.message, err=True)
        typer.echo(f"Next: faultsage {e.next_step}", err=True)
        raise typer.Exit(1) from e
    for m, bak in done:
        typer.echo(f"Applied {m.version:04d} {m.name}" + (f" (backup: {bak})" if bak else ""))
    if not done:
        typer.echo("Nothing to apply.")

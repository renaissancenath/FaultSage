"""Backup and restore of the cloud database (runs on SQLite, and on PostgreSQL in CI)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from typer.testing import CliRunner

from faultsage.cloud.cli import app as cloud_cli
from faultsage.cloud.storage import db
from faultsage.errors import DestructiveMigrationError
from tests.cloud.conftest import signup


def _emails() -> set[str]:
    with db.engine().begin() as c:
        return {r[0] for r in c.execute(text("SELECT email FROM users"))}


def test_backup_then_restore_round_trip(cloud: TestClient, tmp_path: Path) -> None:
    signup(cloud, "before@example.com")
    backup = Path(db.dump(db.engine(), tmp_path / "bk", "manual"))
    assert backup.stat().st_size > 0
    cloud.cookies.clear()
    signup(cloud, "after@example.com")
    assert _emails() == {"before@example.com", "after@example.com"}

    safety = db.restore(
        db.engine(),
        backup,
        environment="development",
        approved_by="Tester",
        backup_dir=tmp_path / "bk",
    )
    assert _emails() == {"before@example.com"}
    assert Path(safety).exists() and Path(safety) != backup
    with db.engine().begin() as c:
        row = c.execute(
            text(
                "SELECT version, approved_by, statements FROM migration_approvals WHERE version = -1"
            )
        ).one()
    assert row[0] == -1 and row[1] == "Tester" and backup.name in row[2]

    # The safety copy really holds the data from before the restore: restoring it brings it back.
    db.restore(
        db.engine(),
        Path(safety),
        environment="development",
        approved_by="Tester",
        backup_dir=tmp_path / "bk",
    )
    assert _emails() == {"before@example.com", "after@example.com"}
    assert cloud.get("/healthz").json() == {"status": "ok"}


def test_restore_refusals_change_nothing(cloud: TestClient, tmp_path: Path) -> None:
    signup(cloud, "keep@example.com")
    good = Path(db.dump(db.engine(), tmp_path, "manual"))
    with pytest.raises(DestructiveMigrationError, match="approved-by"):
        db.restore(db.engine(), good, environment="development", approved_by=" ")
    junk = tmp_path / "junk.dump"
    junk.write_bytes(b"not a backup at all" * 50)
    with pytest.raises(DestructiveMigrationError, match="not"):
        db.restore(db.engine(), junk, environment="development", approved_by="Tester")
    with pytest.raises(DestructiveMigrationError, match="does not exist"):
        db.restore(
            db.engine(), tmp_path / "missing.dump", environment="development", approved_by="T"
        )
    assert _emails() == {"keep@example.com"}


def test_cli_restore_needs_typed_phrase_and_matching_env(cloud: TestClient, tmp_path: Path) -> None:
    signup(cloud, "keep@example.com")
    runner = CliRunner()
    r = runner.invoke(cloud_cli, ["db", "backup", "--out-dir", str(tmp_path)])
    assert r.exit_code == 0, r.output
    dump_file = Path(r.output.split("Backup written: ")[1].strip())
    cloud.cookies.clear()
    signup(cloud, "later@example.com")

    args = [
        "db",
        "restore",
        str(dump_file),
        "--approved-by",
        "Tester",
        "--backup-dir",
        str(tmp_path),
    ]
    r = runner.invoke(cloud_cli, [*args, "--env", "production"])
    assert r.exit_code == 1 and "does not match" in r.output
    r = runner.invoke(cloud_cli, [*args, "--env", "development"], input="yes\n")
    assert r.exit_code == 1 and "Nothing changed" in r.output
    assert "later@example.com" in _emails()
    r = runner.invoke(
        cloud_cli,
        [*args, "--env", "development"],
        input=f"restore {dump_file.name} on development\n",
    )
    assert r.exit_code == 0, r.output
    assert _emails() == {"keep@example.com"}

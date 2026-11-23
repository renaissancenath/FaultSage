"""The destructive-migration gate on the cloud database (SR-26, SR-28)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from faultsage.cloud.storage import db
from faultsage.errors import DestructiveMigrationError


def test_destructive_migration_needs_named_approval_and_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "migrations"
    folder.mkdir()
    (folder / "0001_init.sql").write_text(db.MIGRATIONS.joinpath("0001_init.sql").read_text())
    (folder / "0002_drop_upgrade_requests_destructive.sql").write_text(
        "DROP TABLE upgrade_requests;"
    )
    monkeypatch.setattr(db, "MIGRATIONS", folder)
    eng = db.make_engine(f"sqlite:///{tmp_path / 'c.db'}")
    blocked = db.migrate_safe_on_start(eng)
    assert [m.version for m in blocked] == [2]  # never runs on start
    with pytest.raises(DestructiveMigrationError, match="DROP TABLE upgrade_requests"):
        db.migrate(eng, set(), environment="production")
    with pytest.raises(DestructiveMigrationError, match="approved-by"):
        db.migrate(eng, {2}, environment="production")
    done = db.migrate(
        eng, {2}, environment="production", approved_by="Renaissance", backup_dir=tmp_path / "bk"
    )
    assert done[0][1] and Path(done[0][1]).exists()
    with eng.begin() as c:
        row = c.execute(
            text("SELECT version, environment, approved_by FROM migration_approvals")
        ).one()
    assert tuple(row) == (2, "production", "Renaissance")

"""Local SQLite storage: migrations and the destructive gate, retention, checkpoints, graphs, purge."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from faultsage.errors import DbBusyError, DestructiveMigrationError
from faultsage.storage import db, repo_events, repo_incidents


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.open_store(tmp_path / "fs.db")


def test_local_destructive_migration_needs_approval_and_backs_up(tmp_path: Path) -> None:
    folder = tmp_path / "mig"
    folder.mkdir()
    (folder / "0001_init.sql").write_text(db.MIGRATIONS_DIR.joinpath("0001_init.sql").read_text())
    (folder / "0002_drop_scans_destructive.sql").write_text("DROP TABLE scan_findings;\n")
    path = tmp_path / "x.db"
    c = db.connect(path)
    assert [m.version for m, _ in db.migrate(c, path, folder=folder)] == [1]
    with pytest.raises(DestructiveMigrationError):
        db.migrate(c, path, folder=folder)
    done = db.migrate(c, path, {2}, folder=folder)
    assert done[0][1] is not None and done[0][1].exists()
    assert "scan_findings" not in {
        r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def test_open_store_refuses_corrupt_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database" * 100)
    with pytest.raises(db.DbCorruptError, match="integrity check") as err:
        db.open_store(bad)
    assert "never deletes it" in err.value.next_step


def test_split_keeps_triggers_whole() -> None:
    sql = (
        "CREATE TABLE a (x);\nCREATE TRIGGER t AFTER INSERT ON a BEGIN\n  SELECT 1;\nEND;\n-- end\n"
    )
    assert len(db._split(sql)) == 2


def test_tx_rolls_back_and_nests(conn: sqlite3.Connection) -> None:
    with pytest.raises(RuntimeError), db.tx(conn):
        repo_events.upsert_project(conn, "p", "/p", "3.12", "h")
        raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
    with db.tx(conn), db.tx(conn):
        repo_events.upsert_project(conn, "p", "/p", "3.12", "h")
    assert repo_events.upsert_project(conn, "p2", "/p", "3.12", "h2") == 1  # same root updates


def test_busy_database_reports_db_busy(tmp_path: Path) -> None:
    path = tmp_path / "b.db"
    a, b = db.connect(path), db.connect(path)
    a.execute("CREATE TABLE t (x)")
    a.execute("BEGIN IMMEDIATE")
    b.execute("PRAGMA busy_timeout=10")
    with pytest.raises(DbBusyError), db.tx(b):
        pass
    a.execute("ROLLBACK")


def test_events_checkpoints_graphs_retention_and_purge(conn: sqlite3.Connection) -> None:
    with db.tx(conn):
        pid = repo_events.upsert_project(conn, "p", "/p", "3.12", "h")
        sid = repo_events.start_session(conn, pid, {"pytest": True})
        repo_events.set_session_state(conn, sid, "stopped")
        old = repo_events.insert_event(
            conn, pid, sid, "log_match", "2000-01-01T00:00:00Z", "f", {"t": 1}
        )
        assert (
            repo_events.insert_event(
                conn, pid, sid, "log_match", "2000-01-01T00:00:00Z", "f", {"t": 1}
            )
            is None
        )
        ev = repo_events.insert_event(
            conn, pid, sid, "checkpoint", db.now_iso(), "f", {"step": "s"}
        )
        repo_events.insert_checkpoint(
            conn,
            pid,
            {
                "step": "clean",
                "object_type": "dict",
                "shape": [2],
                "columns": [{"name": "a", "dtype": "int"}],
            },
            db.now_iso(),
            ev or 0,
        )
        repo_events.save_graph(conn, pid, "imports", "hash1", {"nodes": [], "edges": []})
        iid = repo_incidents.create_incident(conn, pid, "sig", "t", "KeyError", db.now_iso())
        repo_incidents.add_occurrence(conn, iid, ev or 0, "abc", db.now_iso(), bump=True)
    assert old and repo_events.event_payload(conn, old) == {"t": 1}
    assert repo_events.recent_events(conn, pid, "log_match")[0]["id"] == old
    assert repo_events.latest_checkpoints(conn, pid)["clean"]["columns"][0]["name"] == "a"
    assert repo_events.load_graph(conn, pid, "imports") == ("hash1", {"nodes": [], "edges": []})
    with db.tx(conn):
        assert repo_events.delete_old_events(conn, pid, 30) == 1
    scan = repo_events.create_scan(conn, pid)
    repo_events.finish_scan(conn, scan, [{"severity": "note", "rule": "r", "message": "m"}])
    assert (
        repo_events.get_scan(conn, scan)["findings_count"] == 1
        and repo_events.get_scan(conn, 99) is None
    )
    assert repo_events.latest_scan_id(conn, pid) == scan
    assert repo_incidents.find_open_by_signature(conn, pid, "sig") is not None
    assert (
        repo_incidents.summary(conn, iid) is not None and repo_incidents.summary(conn, 999) is None
    )
    with db.tx(conn):
        repo_incidents.set_status(conn, iid, "resolved")
    assert repo_incidents.find_closed_by_signature(conn, pid, "sig")["id"] == iid
    assert repo_incidents.case_file(conn, 999) is None
    with db.tx(conn):
        repo_events.purge(conn, pid)
    assert conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 0

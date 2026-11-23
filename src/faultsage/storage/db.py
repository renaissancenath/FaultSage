"""SQLite connection and migrations (DATABASE.md). Only storage/ executes SQL."""

from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from faultsage.errors import DbBusyError, FaultSageError
from faultsage.migration_gate import Migration, check_gate, discover

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class DbCorruptError(FaultSageError):
    code = "db_corrupt"


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=2.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=2000")
    return conn


def integrity_ok(conn: sqlite3.Connection) -> bool:
    row = conn.execute("PRAGMA quick_check").fetchone()
    return bool(row) and row[0] == "ok"


_CONN_LOCKS: dict[int, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def conn_lock(conn: sqlite3.Connection) -> threading.RLock:
    """One lock per connection: API threads and the ingest thread share a connection."""
    with _LOCKS_GUARD:
        return _CONN_LOCKS.setdefault(id(conn), threading.RLock())


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE with retry up to ~2 s on lock (ARCHITECTURE failure table)."""
    lock = conn_lock(conn)
    with lock:
        if conn.in_transaction:  # nested call in the same thread: join the outer transaction
            yield conn
            return
        with _tx(conn):
            yield conn


@contextmanager
def _tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    deadline = time.monotonic() + 2.0
    while True:
        try:
            conn.execute("BEGIN IMMEDIATE")
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or time.monotonic() > deadline:
                raise DbBusyError("The database is busy.", "Retry in a moment.") from exc
            time.sleep(0.05)
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    _ensure_table(conn)
    return {int(r[0]) for r in conn.execute("SELECT version FROM schema_migrations")}


def pending(conn: sqlite3.Connection, folder: Path = MIGRATIONS_DIR) -> list[Migration]:
    done = applied_versions(conn)
    return [m for m in discover(folder) if m.version not in done]


def backup(db_path: Path, version: int) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    target = db_path.with_name(f"{db_path.name}.bak-{version:04d}-{stamp}")
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def migrate(
    conn: sqlite3.Connection,
    db_path: Path | None,
    approve: set[int] | None = None,
    folder: Path = MIGRATIONS_DIR,
) -> list[tuple[Migration, Path | None]]:
    """Apply pending migrations in order. Destructive ones need ``approve`` and get a backup."""
    todo = check_gate(pending(conn, folder), approve or set())
    done: list[tuple[Migration, Path | None]] = []
    for m in todo:
        bak = None
        if m.destructive:
            if db_path is None:
                raise DbCorruptError("Destructive migration needs a file database for backup.")
            bak = backup(db_path, m.version)
        sql = m.sql
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in _split(sql):
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (m.version, m.name, now_iso()),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        done.append((m, bak))
    return done


def _split(sql: str) -> list[str]:
    """Split a migration into statements (sqlite3.complete_statement keeps triggers whole)."""
    out: list[str] = []
    buf = ""
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip() and not buf.strip().startswith("--"):
        out.append(buf.strip())
    return out


def open_store(db_path: Path, approve: set[int] | None = None) -> sqlite3.Connection:
    existed = db_path.exists()
    try:
        conn = connect(db_path)
        healthy = not existed or integrity_ok(conn)
    except sqlite3.DatabaseError:
        healthy = False
    if not healthy:
        raise DbCorruptError(
            f"{db_path} failed its integrity check.",
            "Stop FaultSage, copy the file somewhere safe, then run faultsage purge --all "
            "to start fresh. FaultSage never deletes it for you.",
        )
    migrate(conn, db_path, approve)
    rest = pending(conn)
    if rest:
        conn.close()
        check_gate(rest, set())  # raises with the description of the destructive migration
    return conn


def copy_db(src: Path, dst: Path) -> None:
    shutil.copy2(src, dst)


class ConnectionPerThread:
    """One sqlite3 connection per thread for the same file. Python's sqlite3 objects must not be
    shared between threads that run queries at the same time; WAL mode lets these connections
    read while one writes."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._guard = threading.Lock()

    def get(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.db_path)
            self._local.conn = conn
            with self._guard:
                self._all.append(conn)
        return conn

    def close_all(self) -> None:
        with self._guard:
            for c in self._all:
                c.close()
            self._all.clear()

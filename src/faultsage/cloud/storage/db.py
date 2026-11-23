"""Cloud database access (D-016). SQLAlchemy Core with parameterised text SQL; only
faultsage/cloud/storage executes SQL. Works on PostgreSQL (production) and SQLite (dev, tests).

Destructive migrations (SR-26, SR-28) never run on start. They need
``faultsage-cloud db migrate --approve VERSION --env ENV --approved-by NAME`` with typed
confirmation, a successful backup, and they are recorded in ``migration_approvals``. In production
a backup must succeed or the migration is refused (fail closed).
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event, text

from faultsage.errors import DestructiveMigrationError
from faultsage.migration_gate import Migration, check_gate, destructive_statements, discover

MIGRATIONS = Path(__file__).parent / "migrations"
_ENGINE: Engine | None = None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn: Any, _: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return eng
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        from faultsage.cloud.settings import database_url_from_env

        _ENGINE = make_engine(database_url_from_env())
    return _ENGINE


def set_engine(eng: Engine | None) -> None:
    global _ENGINE
    _ENGINE = eng


@contextmanager
def tx() -> Iterator[Connection]:
    with engine().begin() as conn:
        yield conn


def q(conn: Connection, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def one(conn: Connection, sql: str, **params: Any) -> dict[str, Any] | None:
    r = conn.execute(text(sql), params).mappings().first()
    return dict(r) if r else None


def ex(conn: Connection, sql: str, **params: Any) -> int:
    return conn.execute(text(sql), params).rowcount or 0


def insert(conn: Connection, sql: str, **params: Any) -> int:
    """Run an INSERT ... RETURNING id (PostgreSQL and SQLite 3.35+)."""
    return int(conn.execute(text(sql + " RETURNING id"), params).scalar_one())


# ---- migrations ------------------------------------------------------------------------------


def _render(sql: str, dialect: str) -> str:
    ident = (
        "BIGSERIAL PRIMARY KEY" if dialect == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    )
    return sql.replace("{{ID}}", ident)


def _statements(sql: str) -> list[str]:
    body = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def _ensure_table(conn: Connection) -> None:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
    )


def pending(eng: Engine | None = None) -> list[Migration]:
    e = eng or engine()
    with e.begin() as conn:
        _ensure_table(conn)
        done = {int(r[0]) for r in conn.execute(text("SELECT version FROM schema_migrations"))}
    return [m for m in discover(MIGRATIONS) if m.version not in done]


def _pg_url(eng: Engine) -> str:
    return eng.url.set(drivername="postgresql").render_as_string(hide_password=False)


def _pg_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise DestructiveMigrationError(
            f"{name} is not installed.",
            "Use the FaultSage Docker image (it ships pg_dump and pg_restore 17), or install the "
            "PostgreSQL 17 client tools.",
        )
    return path


def _new_file(path: Path) -> Path:
    """Reserve a file name that did not exist before (raises if it did)."""
    try:
        path.open("xb").close()
    except FileExistsError as e:
        raise DestructiveMigrationError(
            f"{path} already exists; refusing to overwrite a backup.", "Retry in a moment."
        ) from e
    return path


def dump(eng: Engine, out_dir: Path, label: str) -> str:
    """Take a full backup now and return its path. SQLite: online backup API (safe with WAL).
    PostgreSQL: pg_dump custom format, which pg_restore reads."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Microseconds plus an exclusive create: a backup never overwrites an earlier one (two backups
    # in one second used to share a name, so a safety backup could replace the file being restored).
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    url = eng.url
    if url.get_backend_name() == "sqlite":
        src = Path(url.database or "")
        if not src.exists():
            raise DestructiveMigrationError(
                "SQLite database file not found for backup.", "Check DATABASE_URL."
            )
        dest = _new_file(out_dir / f"{src.name}.bak-{label}-{stamp}")
        with sqlite3.connect(src) as live, sqlite3.connect(dest) as copy:
            live.backup(copy)
        return str(dest)
    dest = _new_file(out_dir / f"faultsage-{label}-{stamp}.dump")
    res = subprocess.run(
        [_pg_tool("pg_dump"), "--format=custom", f"--file={dest}", _pg_url(eng)],
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if res.returncode != 0:
        raise DestructiveMigrationError(
            "pg_dump failed: " + res.stderr[-500:], "Fix the backup, then retry."
        )
    return str(dest)


def backup(eng: Engine, version: int, out_dir: Path) -> str:
    """Back up before a destructive migration."""
    return dump(eng, out_dir, f"{version:04d}")


def _check_dump(eng: Engine, dump_file: Path) -> None:
    if not dump_file.is_file():
        raise DestructiveMigrationError(f"{dump_file} does not exist.", "Check the path.")
    if eng.url.get_backend_name() == "sqlite":
        try:
            with sqlite3.connect(f"file:{dump_file}?mode=ro", uri=True) as c:
                ok = c.execute("PRAGMA integrity_check").fetchone()
                has = c.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'schema_migrations'"
                ).fetchone()
        except sqlite3.DatabaseError as e:
            raise DestructiveMigrationError(
                f"{dump_file} is not a SQLite database.", "Pick a FaultSage backup file."
            ) from e
        if not ok or ok[0] != "ok" or not has:
            raise DestructiveMigrationError(
                f"{dump_file} is damaged or not a FaultSage backup.", "Pick another backup."
            )
        return
    res = subprocess.run(
        [_pg_tool("pg_restore"), "--list", str(dump_file)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if res.returncode != 0 or "schema_migrations" not in res.stdout:
        raise DestructiveMigrationError(
            f"{dump_file} is not a readable FaultSage pg_dump file.", "Pick another backup."
        )


# pg_dump 17 writes "SET transaction_timeout = 0;", which PostgreSQL 16 servers reject. The line
# only disables a timeout during the restore, so dropping it is safe on every version.
_SKIP_LINES = (b"SET transaction_timeout",)


def _pg_restore_stream(eng: Engine, dump_file: Path) -> str:
    """pg_restore (as SQL) -> filter -> psql, all in one transaction. Returns stderr on failure."""
    producer = subprocess.Popen(
        [
            _pg_tool("pg_restore"),
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--file=-",
            str(dump_file),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    consumer = subprocess.Popen(
        [
            _pg_tool("psql"),
            "--no-psqlrc",
            "--quiet",
            "--single-transaction",
            "--set=ON_ERROR_STOP=1",
            f"--dbname={_pg_url(eng)}",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if producer.stdout is None or consumer.stdin is None:  # pragma: no cover - PIPE always set
        raise DestructiveMigrationError("Could not start the restore tools.", "")
    try:
        for line in producer.stdout:
            if not line.startswith(_SKIP_LINES):
                consumer.stdin.write(line)
    except BrokenPipeError:
        pass  # psql stopped on an error; its stderr says why
    finally:
        with suppress(BrokenPipeError):
            consumer.stdin.close()
    p_err = producer.stderr.read().decode(errors="replace") if producer.stderr else ""
    c_err = consumer.stderr.read().decode(errors="replace") if consumer.stderr else ""
    if producer.wait(timeout=3600) != 0:
        consumer.kill()
        return "pg_restore: " + p_err
    if consumer.wait(timeout=3600) != 0:
        return "psql: " + c_err
    return ""


def restore(
    eng: Engine,
    dump_file: Path,
    *,
    environment: str,
    approved_by: str,
    backup_dir: Path = Path("backups"),
) -> str:
    """Replace the whole database with a backup. Destructive: needs a named approver, checks the
    file first, and takes a backup of the current data before touching anything (fail closed).
    Returns the path of that safety backup. The approval is recorded after the restore, so the
    record survives it."""
    if not approved_by.strip():
        raise DestructiveMigrationError(
            "A restore needs --approved-by NAME.", "Say who approved it."
        )
    _check_dump(eng, dump_file)
    safety = dump(eng, backup_dir, "before-restore")
    if eng.url.get_backend_name() == "sqlite":
        eng.dispose()
        live = Path(eng.url.database or "")
        with sqlite3.connect(dump_file) as src, sqlite3.connect(live) as dst:
            src.backup(dst)
    else:
        err = _pg_restore_stream(eng, dump_file)
        if err:
            raise DestructiveMigrationError(
                "The restore failed and was rolled back; the database is unchanged: " + err[-500:],
                f"Your data is also saved in {safety}.",
            )
    with eng.begin() as conn:
        _ensure_table(conn)
        conn.execute(
            text(
                "INSERT INTO migration_approvals(version, environment, approved_by, approved_at, "
                "backup_ref, statements) VALUES (:v, :e, :b, :t, :r, :s)"
            ),
            {
                "v": -1,
                "e": environment,
                "b": approved_by,
                "t": now_iso(),
                "r": safety,
                "s": f"RESTORE FROM {dump_file.name}",
            },
        )
    return safety


def migrate(
    eng: Engine | None = None,
    approve: set[int] | None = None,
    *,
    environment: str = "development",
    approved_by: str = "",
    backup_dir: Path = Path("backups"),
    backup_ref: str | None = None,
) -> list[tuple[Migration, str | None]]:
    e = eng or engine()
    approve = approve or set()
    todo = check_gate(pending(e), approve)
    dialect = e.dialect.name
    done: list[tuple[Migration, str | None]] = []
    for m in todo:
        ref = None
        if m.destructive:
            if not approved_by.strip():
                raise DestructiveMigrationError(
                    "A destructive migration needs --approved-by NAME.", "Say who approved it."
                )
            ref = backup_ref or backup(e, m.version, backup_dir)
        with e.begin() as conn:
            for stmt in _statements(_render(m.sql, dialect)):
                conn.execute(text(stmt))
            conn.execute(
                text(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (:v, :n, :t)"
                ),
                {"v": m.version, "n": m.name, "t": now_iso()},
            )
            if m.destructive:
                conn.execute(
                    text(
                        "INSERT INTO migration_approvals(version, environment, approved_by, approved_at, backup_ref, "
                        "statements) VALUES (:v, :e, :b, :t, :r, :s)"
                    ),
                    {
                        "v": m.version,
                        "e": environment,
                        "b": approved_by,
                        "t": now_iso(),
                        "r": ref or "",
                        "s": "; ".join(destructive_statements(m.sql)),
                    },
                )
        done.append((m, ref))
    return done


def migrate_safe_on_start(eng: Engine | None = None) -> list[Migration]:
    """App start: apply only non-destructive migrations. Report (never run) destructive ones."""
    e = eng or engine()
    todo = pending(e)
    safe: list[Migration] = []
    for m in todo:
        if m.destructive:
            break
        safe.append(m)
    if safe:
        migrate(e, set())
    return [m for m in todo if m not in safe]

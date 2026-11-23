"""Shared rules for numbered SQL migrations and the destructive-migration gate (SR-26, SR-28).

Used by the local SQLite store and by FaultSage Cloud. A migration is destructive when it drops,
renames or deletes. Destructive files must end in ``_destructive.sql``; a file that contains
destructive SQL without that suffix is refused outright, so nothing slips through by naming.
Destructive migrations never run without an approval for that exact version, in that exact
environment, given at the moment of the run. Approvals never carry over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from faultsage.errors import DestructiveMigrationError

_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
_DESTRUCTIVE_SQL = re.compile(
    r"\b(DROP\s+(TABLE|INDEX|VIEW|COLUMN|SCHEMA|TRIGGER)|DELETE\s+FROM|TRUNCATE|"
    r"ALTER\s+TABLE\s+\S+\s+(DROP|RENAME)|RENAME\s+TO)\b",
    re.I,
)
_COMMENT = re.compile(r"--[^\n]*")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    destructive: bool

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def destructive_statements(sql: str) -> list[str]:
    body = _COMMENT.sub("", sql)
    return [s.strip() for s in body.split(";") if _DESTRUCTIVE_SQL.search(s)]


def discover(folder: Path) -> list[Migration]:
    found: list[Migration] = []
    for p in sorted(folder.glob("*.sql")):
        m = _NAME.match(p.name)
        if not m:
            raise DestructiveMigrationError(
                f"Migration file name {p.name} does not match NNNN_name.sql.", "Rename the file."
            )
        marked = p.name.endswith("_destructive.sql")
        has_destructive = bool(destructive_statements(p.read_text(encoding="utf-8")))
        if has_destructive and not marked:
            raise DestructiveMigrationError(
                f"{p.name} contains DROP, DELETE, TRUNCATE or RENAME but is not named "
                "*_destructive.sql.",
                "Rename it so the approval gate applies, then ask for approval.",
            )
        found.append(Migration(int(m.group(1)), m.group(2), p, marked))
    versions = [m.version for m in found]
    if len(versions) != len(set(versions)):
        raise DestructiveMigrationError("Two migrations share a version number.", "Renumber one.")
    return found


def describe(m: Migration) -> str:
    stmts = destructive_statements(m.sql)
    lines = [f"Migration {m.version:04d} {m.name} is destructive. It will run:"]
    lines += [f"  {s}" for s in stmts]
    lines.append("Data in the affected tables or columns will be lost. A backup is taken first.")
    return "\n".join(lines)


def check_gate(pending: list[Migration], approved_versions: set[int]) -> list[Migration]:
    """Return the migrations allowed to run now. Stops at the first unapproved destructive one,
    raising with its full description, so later migrations never jump ahead of it."""
    allowed: list[Migration] = []
    for m in pending:
        if m.destructive and m.version not in approved_versions:
            if allowed:
                break  # run safe ones before it; the next run will stop here and raise
            raise DestructiveMigrationError(
                describe(m),
                f"Review it, then approve this one run with: db migrate --approve {m.version}",
            )
        allowed.append(m)
    return allowed

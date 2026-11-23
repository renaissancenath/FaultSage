from __future__ import annotations

import pytest

from faultsage.errors import DestructiveMigrationError
from faultsage.fixes.patch import PatchError, apply, make_diff, parse
from faultsage.migration_gate import check_gate, discover


def test_diff_roundtrip() -> None:
    old = "a\nb\nc\n"
    new = "a\nB\nc\n"
    fp = parse(make_diff("x.py", old, new))[0]
    assert fp.path == "x.py"
    assert apply(old, fp) == new


def test_apply_refuses_changed_context() -> None:
    fp = parse(make_diff("x.py", "a\nb\nc\n", "a\nB\nc\n"))[0]
    with pytest.raises(PatchError):
        apply("a\nCHANGED\nc\n", fp)


def test_destructive_sql_in_safe_name_is_refused(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "0001_init.sql").write_text("CREATE TABLE a (id INTEGER);")
    (tmp_path / "0002_cleanup.sql").write_text("DROP TABLE a;")
    with pytest.raises(DestructiveMigrationError, match="not named"):
        discover(tmp_path)


def test_destructive_migration_needs_approval_every_time(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "0001_init.sql").write_text("CREATE TABLE a (id INTEGER);")
    (tmp_path / "0002_drop_a_destructive.sql").write_text("-- drop old table\nDROP TABLE a;")
    ms = discover(tmp_path)
    assert check_gate(ms, set()) == [ms[0]]  # safe one runs, stops before the destructive one
    with pytest.raises(DestructiveMigrationError, match="DROP TABLE a"):
        check_gate(ms[1:], set())
    assert check_gate(ms[1:], {2}) == [ms[1]]
    with pytest.raises(DestructiveMigrationError):
        check_gate(ms[1:], {3})  # approving a different version does not count

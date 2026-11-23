"""SR-11 to SR-14: every refusal path of the apply gate leaves files untouched."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultsage.errors import PatchStaleError, PathOutsideProjectError
from faultsage.fixes.apply_gate import apply_suggestion
from faultsage.fixes.patch import make_diff, sha256_text
from faultsage.models.core import Suggestion


def sug(path: str, old: str, new: str, **kw: object) -> Suggestion:
    base = {
        "explanation": "x",
        "patch_diff": make_diff(path, old, new),
        "base_hashes": {path: sha256_text(old)},
    }
    base.update(kw)
    return Suggestion(**base)  # type: ignore[arg-type]


def test_refusals(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("a\nb\n")
    bk = tmp_path / ".faultsage" / "backups"
    assert apply_suggestion(tmp_path, bk, 0, sug("a.py", "a\nb\n", "a\nB\n")).outcome == "refused"
    assert apply_suggestion(tmp_path, bk, 1, Suggestion(explanation="x")).outcome == "refused"
    assert (
        apply_suggestion(tmp_path, bk, 1, sug("a.py", "a\nb\n", "a\nB\n", state="applied")).outcome
        == "refused"
    )
    with pytest.raises(PatchStaleError):
        apply_suggestion(tmp_path, bk, 1, sug("a.py", "a\nb\n", "a\nB\n", state="stale"))
    assert (
        apply_suggestion(tmp_path, bk, 1, sug("a.py", "a\nb\n", "a\nB\n", base_hashes={})).outcome
        == "refused"
    )
    assert (
        apply_suggestion(tmp_path, bk, 1, Suggestion(explanation="x", patch_diff="garbage")).outcome
        == "refused"
    )
    with pytest.raises(PathOutsideProjectError):
        apply_suggestion(tmp_path, bk, 1, sug("../evil.py", "a\n", "b\n"))
    outside = tmp_path.parent / f"{tmp_path.name}-target.py"
    outside.write_text("a\nb\n")
    (tmp_path / "link.py").symlink_to(outside)
    with pytest.raises(PathOutsideProjectError):
        apply_suggestion(tmp_path, bk, 1, sug("link.py", "a\nb\n", "a\nB\n"))
    f.write_text("changed\n")
    with pytest.raises(PatchStaleError):
        apply_suggestion(tmp_path, bk, 1, sug("a.py", "a\nb\n", "a\nB\n"))
    assert f.read_text() == "changed\n" and outside.read_text() == "a\nb\n"


def test_successful_apply_outside_git_writes_backup(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("a\nb\n")
    out = apply_suggestion(tmp_path, tmp_path / "bk", 7, sug("a.py", "a\nb\n", "a\nB\n"))
    assert out.outcome == "applied" and f.read_text() == "a\nB\n"
    assert (tmp_path / "bk" / "7" / "a.py").read_text() == "a\nb\n"

"""The approval gate (F10, FR-24, SR-11 to SR-14). The ONLY module that writes project files.

Order of checks, all fail closed:
1. An approval record exists for this suggestion (created by the caller before calling apply).
2. Every target path resolves inside the project root (symlink escape refused).
3. Base file hashes match the suggestion (else stale).
4. Git tree is clean, unless the user confirmed a stash.
5. Backup of every target is written to .faultsage/backups/<approval_id>/.
6. Patch applied; any failure restores the backup.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from faultsage.collectors.git_reader import dirty_files, is_repo
from faultsage.errors import GitDirtyError, PatchStaleError
from faultsage.fixes.patch import PatchError, apply, parse, sha256_text
from faultsage.models.core import Suggestion
from faultsage.paths import inside_root, secure_mkdir


@dataclass(frozen=True, slots=True)
class ApplyOutcome:
    outcome: str  # applied | refused | failed_restored
    detail: str
    backup_path: str | None


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".faultsage-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        shutil.copymode(path, tmp)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def apply_suggestion(
    root: Path,
    backups_dir: Path,
    approval_id: int,
    suggestion: Suggestion,
    *,
    stash_confirmed: bool = False,
) -> ApplyOutcome:
    if approval_id <= 0:
        return ApplyOutcome("refused", "No approval record. Nothing was changed.", None)
    if not suggestion.patch_diff:
        return ApplyOutcome("refused", "This suggestion has no patch.", None)
    if suggestion.state == "stale":
        raise PatchStaleError(
            "A file changed since this suggestion was made.",
            "Regenerate the suggestion from the case file.",
        )
    if suggestion.state not in ("proposed",):
        return ApplyOutcome(
            "refused", f"Suggestion is {suggestion.state}; only proposed patches apply.", None
        )
    try:
        file_patches = parse(suggestion.patch_diff)
    except PatchError as exc:
        return ApplyOutcome("refused", str(exc), None)
    targets: dict[str, Path] = {}
    for fp in file_patches:
        resolved = inside_root(root, fp.path)  # raises PathOutsideProjectError
        if resolved.is_symlink():
            return ApplyOutcome(
                "refused", f"{fp.path} is a symlink; refusing to write through it.", None
            )
        if fp.path not in suggestion.base_hashes:
            return ApplyOutcome("refused", f"{fp.path} has no recorded base hash.", None)
        targets[fp.path] = resolved
    originals: dict[str, str] = {}
    for rel, path in targets.items():
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if sha256_text(current) != suggestion.base_hashes[rel]:
            raise PatchStaleError(
                f"{rel} changed since this suggestion was made.",
                "Regenerate the suggestion from the case file.",
            )
        originals[rel] = current
    if is_repo(root) and not stash_confirmed:
        dirty = dirty_files(root)
        if dirty:
            raise GitDirtyError(
                "Git tree has uncommitted changes: " + ", ".join(dirty[:10]),
                "Commit or stash them (git stash), then apply again.",
            )
    backup_root = secure_mkdir(backups_dir / str(approval_id))
    for rel, text in originals.items():
        dest = backup_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    written: list[str] = []
    try:
        new_texts = {fp.path: apply(originals[fp.path], fp) for fp in file_patches}
        for rel, text in new_texts.items():
            _atomic_write(targets[rel], text)
            written.append(rel)
    except (PatchError, OSError) as exc:
        for rel in written:
            _atomic_write(targets[rel], originals[rel])
        return ApplyOutcome(
            "failed_restored", f"Patch did not apply ({exc}). Files restored.", str(backup_root)
        )
    return ApplyOutcome("applied", f"Applied to {len(written)} file(s).", str(backup_root))

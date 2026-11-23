"""Read-only git access (FR-10). Hooks and fsmonitor disabled (attack surface #13)."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

GIT_TIMEOUT = 30
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(slots=True)
class FileChange:
    path: str
    hunks: list[tuple[int, int]] = field(default_factory=list)  # (start, end) in new file
    commit_time: int | None = None


def _git(root: Path, hooks_dir: Path | None, *args: str) -> str | None:
    hooks = str(hooks_dir) if hooks_dir else "/dev/null"
    cmd = [
        "git",
        "-c",
        f"core.hooksPath={hooks}",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(root),
        *args,
    ]
    try:
        res = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0:
        return None
    return res.stdout


def is_repo(root: Path) -> bool:
    return _git(root, None, "rev-parse", "--is-inside-work-tree") is not None


def head(root: Path) -> tuple[str | None, str | None]:
    sha = _git(root, None, "rev-parse", "--short", "HEAD")
    branch = _git(root, None, "rev-parse", "--abbrev-ref", "HEAD")
    return (sha.strip() if sha else None, branch.strip() if branch else None)


def dirty_files(root: Path) -> list[str]:
    out = _git(root, None, "status", "--porcelain", "--untracked-files=no")
    if out is None:
        return []
    return [line[3:].strip() for line in out.splitlines() if line.strip()]


def parse_diff(diff: str) -> dict[str, FileChange]:
    changes: dict[str, FileChange] = {}
    current: FileChange | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target == "/dev/null":
                current = None
                continue
            path = target[2:] if target.startswith("b/") else target
            current = changes.setdefault(path, FileChange(path))
        elif line.startswith("@@") and current is not None:
            m = _HUNK.match(line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                current.hunks.append((start, start + max(count, 1) - 1))
    return changes


def recent_changes(
    root: Path, since_ref: str | None = None, max_commits: int = 20
) -> dict[str, FileChange]:
    """Changed files and hunks: working tree vs HEAD plus the last ``max_commits`` commits
    (or since ``since_ref``, the last green run)."""
    changes: dict[str, FileChange] = {}
    work = _git(root, None, "diff", "--unified=0", "HEAD", "--", "*.py")
    if work:
        changes.update(parse_diff(work))
    base = since_ref
    if base is None:
        count = _git(root, None, "rev-list", "--count", "HEAD")
        total = int(count.strip()) if count and count.strip().isdigit() else 0
        n = min(max_commits, total - 1)  # HEAD~n must exist
        base = f"HEAD~{n}" if n > 0 else None
    if base:
        hist = _git(root, None, "diff", "--unified=0", base, "HEAD", "--", "*.py")
        if hist:
            for path, ch in parse_diff(hist).items():
                existing = changes.setdefault(path, FileChange(path))
                existing.hunks.extend(ch.hunks)
    for path, ch in changes.items():
        t = _git(root, None, "log", "-1", "--format=%ct", "--", path)
        ch.commit_time = int(t.strip()) if t and t.strip().isdigit() else None
    return changes

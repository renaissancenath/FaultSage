"""Path containment helpers (SR-12)."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from faultsage.errors import PathOutsideProjectError

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".faultsage",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
        ".tox",
        ".eggs",
        "site-packages",
    }
)


def inside_root(root: Path, candidate: str | Path) -> Path:
    """Resolve ``candidate`` against ``root`` and return it if it stays inside ``root``.

    Symlinks are resolved first, so a link pointing outside the root is refused.
    Raises PathOutsideProjectError otherwise.
    """
    root_resolved = root.resolve(strict=False)
    path = Path(candidate)
    if not path.is_absolute():
        path = root_resolved / path
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathOutsideProjectError(
            f"{candidate} is outside the project root.",
            "Only files inside the project can be read or changed.",
        ) from exc
    return resolved


def is_inside(root: Path, candidate: str | Path) -> bool:
    try:
        inside_root(root, candidate)
    except PathOutsideProjectError:
        return False
    return True


def to_posix_rel(root: Path, path: str | Path) -> str:
    """Return ``path`` relative to ``root`` in POSIX style, or the original string if outside."""
    p = Path(path)
    try:
        return p.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()
    except ValueError:
        return Path(path).as_posix()


def is_ignored(rel_posix: str) -> bool:
    return any(part in IGNORED_DIRS for part in rel_posix.split("/"))


def find_project_root(start: Path) -> Path | None:
    """FR-1: nearest folder with pyproject.toml, setup.py, requirements*.txt or .git."""
    current = start.resolve()
    for folder in [current, *current.parents]:
        if (folder / "pyproject.toml").exists() or (folder / "setup.py").exists():
            return folder
        if any(folder.glob("requirements*.txt")) or (folder / ".git").exists():
            return folder
    return None


def secure_mkdir(path: Path) -> Path:
    """Create a directory with user-only permissions where the OS supports it (SR-15)."""
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def list_python_files(root: Path, limit: int = 5000) -> list[str]:
    """Relative POSIX paths of .py files under ``root``, skipping ignored folders."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = to_posix_rel(root, dirpath)
        prefix = "" if rel_dir in (".", "") else rel_dir + "/"
        dirnames[:] = sorted(d for d in dirnames if not is_ignored(prefix + d))
        for f in sorted(filenames):
            if f.endswith(".py"):
                out.append(prefix + f)
                if len(out) >= limit:
                    return sorted(out)
    return sorted(out)

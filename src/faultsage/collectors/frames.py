"""Turn live Python exceptions and traceback objects into ExceptionInfo models."""

from __future__ import annotations

import linecache
import sys
import traceback
from pathlib import Path
from types import TracebackType

from faultsage.models.core import ExceptionInfo, Frame
from faultsage.paths import is_ignored, to_posix_rel
from faultsage.redact import redact

_SITE_MARKERS = ("site-packages", "dist-packages", "/lib/python", "\\lib\\python")


def is_project_path(root: Path, filename: str) -> bool:
    """FR-15: project frames are under the root and not in a virtualenv or site-packages."""
    if filename.startswith("<"):
        return False
    try:
        rel = Path(filename).resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    rel_posix = rel.as_posix()
    if is_ignored(rel_posix):
        return False
    lowered = filename.replace("\\", "/").lower()
    return not any(m.replace("\\", "/") in lowered for m in _SITE_MARKERS)


def display_path(root: Path, filename: str) -> str:
    if is_project_path(root, filename):
        return to_posix_rel(root, filename)
    norm = filename.replace("\\", "/")
    for marker in ("site-packages/", "dist-packages/"):
        if marker in norm:
            return "<external>/" + norm.split(marker, 1)[1]
    if norm.startswith("<"):
        return norm
    return "<external>/" + Path(norm).name


def frames_from_tb(root: Path, tb: TracebackType | None) -> list[Frame]:
    frames: list[Frame] = []
    for fs in traceback.extract_tb(tb):
        line = fs.line or linecache.getline(fs.filename, fs.lineno or 0).strip() or None
        frames.append(
            Frame(
                file_path=display_path(root, fs.filename),
                line=fs.lineno,
                function=fs.name,
                is_project=is_project_path(root, fs.filename),
                code=redact(line)[:500] if line else None,
            )
        )
    return frames


def exception_info(root: Path, exc: BaseException, _seen: set[int] | None = None) -> ExceptionInfo:
    seen = _seen if _seen is not None else set()
    seen.add(id(exc))
    cause = exc.__cause__
    context = None if exc.__suppress_context__ else exc.__context__
    return ExceptionInfo(
        type=type(exc).__qualname__,
        message=redact(str(exc))[:2000],
        frames=frames_from_tb(root, exc.__traceback__),
        cause=exception_info(root, cause, seen) if cause and id(cause) not in seen else None,
        context=exception_info(root, context, seen)
        if context and id(context) not in seen
        else None,
    )


def current_exception_info(root: Path) -> ExceptionInfo | None:
    exc = sys.exception()
    return exception_info(root, exc) if exc is not None else None

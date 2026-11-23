"""Incident signatures and grouping (FR-12, FR-13)."""

from __future__ import annotations

import re
from typing import Any

from faultsage.models.core import ExceptionInfo

_NUM = re.compile(r"\d+")


def normalise_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./").lower()


def signature(exc: ExceptionInfo | None, fallback: str) -> str:
    """exception type + normalised innermost project frame path + function name."""
    if exc is None:
        return f"noexc|{fallback}"
    frame = exc.innermost_project_frame()
    if frame is None and exc.frames:
        frame = exc.frames[-1]
    if frame is None:
        return f"{exc.type}|<no frame>|{fallback}"
    return f"{exc.type}|{normalise_path(frame.file_path)}|{frame.function}"


def title_for(kind: str, body: dict[str, Any], exc: ExceptionInfo | None) -> str:
    """One factual sentence."""
    if kind == "test_result":
        test = str(body.get("node_id", "")).split("::")[-1] or "test"
        subject = f"{test} failed"
        if body.get("phase") in ("setup", "teardown"):
            subject = f"{test} errored in {body['phase']}"
    elif kind == "run_result":
        argv = body.get("argv") or []
        subject = f"{' '.join(argv[:4])[:80]} exited with code {body.get('exit_code')}"
    elif kind == "log_match":
        subject = f"Error in {body.get('file')} line {body.get('line_no')}"
    else:
        subject = kind.replace("_", " ")
    if exc is None:
        return subject
    frame = exc.innermost_project_frame()
    where = (
        f" in {frame.file_path.rsplit('/', 1)[-1]} line {frame.line}"
        if frame and frame.line
        else ""
    )
    msg = exc.message.splitlines()[0][:120] if exc.message else ""
    return f"{subject}: {exc.type}{(' ' + msg) if msg else ''}{where}"

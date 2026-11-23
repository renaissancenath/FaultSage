"""Parse CPython tracebacks from text (FR-14): chained exceptions and pytest long/short formats.

Pure function. Used for stderr tails, log lines and tracebacks pasted or sent to the cloud.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from faultsage.models.core import ExceptionInfo, Frame

_HEADER = "Traceback (most recent call last):"
_CAUSE = "The above exception was the direct cause of the following exception:"
_CONTEXT = "During handling of the above exception, another exception occurred:"
_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>.+))?\s*$')
# pytest short/long: "path/to/file.py:47: KeyError" or "path/file.py:47: in func"
_PYTEST_LOC = re.compile(
    r"^(?P<file>[^\s:][^:\n]*\.py):(?P<line>\d+):\s*(?:in (?P<func>\S+)|(?P<exc>[A-Za-z_][\w.]*))?\s*$"
)
_PYTEST_E = re.compile(r"^E\s{1,8}(?P<text>.*)$")
_EXC_LINE = re.compile(
    r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Iteration|[A-Z]\w*))(?::\s?(?P<msg>.*))?$"
)
_CARET = re.compile(r"^\s*[\^~\-\s]+$")

IsProject = Callable[[str], bool]


def _not_project(_: str) -> bool:
    return False


def _parse_block(lines: list[str], is_project: IsProject) -> ExceptionInfo | None:
    frames: list[Frame] = []
    i = 0
    exc_type: str | None = None
    msg_lines: list[str] = []
    while i < len(lines):
        line = lines[i]
        m = _FRAME.match(line)
        if m:
            code = None
            if (
                i + 1 < len(lines)
                and not _FRAME.match(lines[i + 1])
                and lines[i + 1].startswith("    ")
            ):
                nxt = lines[i + 1].strip()
                if nxt and not _CARET.match(lines[i + 1]):
                    code = nxt
                    i += 1
            path = m.group("file")
            frames.append(
                Frame(
                    file_path=path,
                    line=int(m.group("line")),
                    function=(m.group("func") or "<module>").strip(),
                    is_project=is_project(path),
                    code=code,
                )
            )
            i += 1
            continue
        if _CARET.match(line) and line.strip():
            i += 1
            continue
        if frames and exc_type is None:
            em = _EXC_LINE.match(line.strip())
            if em and not line.startswith(" "):
                exc_type = em.group("type")
                if em.group("msg"):
                    msg_lines.append(em.group("msg"))
                i += 1
                # Multi-line messages continue until a blank line.
                while i < len(lines) and lines[i].strip() and not _FRAME.match(lines[i]):
                    msg_lines.append(lines[i].rstrip())
                    i += 1
                break
        i += 1
    if exc_type is None:
        return None
    return ExceptionInfo(
        type=exc_type.split(".")[-1] if "." in exc_type and exc_type[0].islower() else exc_type,
        message="\n".join(msg_lines)[:2000],
        frames=frames,
    )


def parse_cpython(text: str, is_project: IsProject = _not_project) -> ExceptionInfo | None:
    """Parse the last (outermost raised) exception and link its cause/context chain."""
    lines = text.replace("\r\n", "\n").splitlines()
    blocks: list[tuple[str | None, list[str]]] = []
    link: str | None = None
    current: list[str] | None = None
    for line in lines:
        stripped = line.strip()
        if stripped == _HEADER:
            current = []
            blocks.append((link, current))
            link = None
            continue
        if stripped == _CAUSE:
            link, current = "cause", None
            continue
        if stripped == _CONTEXT:
            link, current = "context", None
            continue
        if current is not None:
            current.append(line)
    parsed: list[tuple[str | None, ExceptionInfo]] = []
    for lk, blk in blocks:
        info = _parse_block(blk, is_project)
        if info is not None:
            parsed.append((lk, info))
    if not parsed:
        return None
    # Only an explicit "direct cause" or "during handling" marker links two blocks. A block
    # without a marker is a separate failure (for example the next failing test in a log), so
    # the first chain is the one returned.
    result = parsed[0][1]
    for lk, info in parsed[1:]:
        if lk is None:
            break
        info = info.model_copy(update={"cause": result} if lk == "cause" else {"context": result})
        result = info
    return result


def parse_pytest(text: str, is_project: IsProject = _not_project) -> ExceptionInfo | None:
    """Parse pytest long or short output (``file.py:47: in func`` lines and ``E`` lines)."""
    if _HEADER in text:
        cp = parse_cpython(text, is_project)
        if cp is not None:
            return cp
    frames: list[Frame] = []
    e_lines: list[str] = []
    last_code: str | None = None
    for raw in text.replace("\r\n", "\n").splitlines():
        em = _PYTEST_E.match(raw)
        if em:
            e_lines.append(em.group("text"))
            continue
        if raw.startswith(">   "):
            last_code = raw[4:].strip()
            continue
        lm = _PYTEST_LOC.match(raw.strip())
        if lm:
            path = lm.group("file")
            frames.append(
                Frame(
                    file_path=path,
                    line=int(lm.group("line")),
                    function=lm.group("func") or "<unknown>",
                    is_project=is_project(path),
                    code=last_code,
                )
            )
            last_code = None
    exc_type, msg = None, ""
    for line in e_lines:
        m = _EXC_LINE.match(line.strip())
        if m and m.group("type")[0].isupper():
            exc_type, msg = m.group("type"), m.group("msg") or ""
            break
    if exc_type is None:
        for f in frames:
            if (
                f.function
                and f.function[0].isupper()
                and f.function.endswith(("Error", "Exception"))
            ):
                exc_type = f.function
        if exc_type is None and e_lines:
            exc_type = "AssertionError"
            msg = e_lines[0]
    if exc_type is None:
        return None
    # Function names missing in the long format ("<unknown>") are filled from the AST index later.
    return ExceptionInfo(type=exc_type, message=msg[:2000], frames=frames)


def parse_any(text: str, is_project: IsProject = _not_project) -> ExceptionInfo | None:
    return parse_cpython(text, is_project) or parse_pytest(text, is_project)

"""Unified diff building and strict application (FR-23). Pure functions on text."""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    pass


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def make_diff(path: str, old: str, new: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    )
    out = []
    for line in lines:
        out.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return "".join(out)


@dataclass(slots=True)
class FilePatch:
    path: str
    hunks: list[tuple[int, list[str]]]  # (old_start, lines with prefix)


def parse(diff: str) -> list[FilePatch]:
    patches: list[FilePatch] = []
    current: FilePatch | None = None
    hunk: list[str] | None = None
    for line in diff.splitlines():
        if line.startswith("--- "):
            continue
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = target[2:] if target.startswith("b/") else target
            current = FilePatch(path, [])
            patches.append(current)
            hunk = None
            continue
        m = _HUNK.match(line)
        if m and current is not None:
            hunk = []
            current.hunks.append((int(m.group(1)), hunk))
            continue
        if line.startswith("\\"):
            continue
        if hunk is not None and line[:1] in (" ", "+", "-"):
            hunk.append(line)
    if not patches:
        raise PatchError("Patch has no file sections.")
    return patches


def apply(old: str, fp: FilePatch) -> str:
    """Apply hunks exactly. Any context mismatch raises PatchError (no fuzz)."""
    src = old.splitlines()
    trailing_nl = old.endswith("\n")
    out: list[str] = []
    pos = 0
    for start, lines in fp.hunks:
        idx = max(start - 1, 0)
        if idx < pos:
            raise PatchError("Overlapping hunks.")
        out.extend(src[pos:idx])
        pos = idx
        for line in lines:
            tag, text = line[0], line[1:]
            if tag in (" ", "-"):
                if pos >= len(src) or src[pos] != text:
                    raise PatchError(f"{fp.path}: context does not match at line {pos + 1}.")
                if tag == " ":
                    out.append(text)
                pos += 1
            else:
                out.append(text)
    out.extend(src[pos:])
    result = "\n".join(out)
    return result + "\n" if trailing_nl or not old else result

"""Triage for production-only bugs (RELEASE_AND_OPERATIONS.md section 5).

Input: a ``faultsage self-report --export`` file, an incident JSON export, or a FaultSage Cloud
issue export. Output: a Markdown triage note with duplicate groups, the likely location, and a
draft failing test built only from the captured data. A human (or their coding agent, using the
triage prompt in docs/PROMPTS.md) writes the fix PR; nothing here edits code or opens PRs.
"""

from __future__ import annotations

from typing import Any

from faultsage.analysis.traceback_parser import parse_cpython
from faultsage.models.core import ExceptionInfo


def _exc_from(entry: dict[str, Any]) -> ExceptionInfo | None:
    if entry.get("exception"):
        return ExceptionInfo.model_validate(entry["exception"])
    tb = entry.get("traceback") or entry.get("sample", {}).get("traceback") or ""
    return parse_cpython(tb, lambda p: "faultsage" in p.replace("\\", "/") or not p.startswith("<"))


def _test_draft(name: str, exc: ExceptionInfo) -> str:
    frame = exc.innermost_project_frame() or (exc.frames[-1] if exc.frames else None)
    target = f"{frame.file_path}:{frame.line} in {frame.function}" if frame else "unknown location"
    msg = exc.message.splitlines()[0][:80] if exc.message else ""
    return "\n".join(
        [
            "```python",
            f"# Draft regression test for {name}. Built from the captured report only.",
            f"# Failure: {exc.type}: {msg}",
            f"# Raised at {target}",
            "import pytest",
            "",
            "",
            f"def test_{name.lower().replace('-', '_')}_regression():",
            "    # Arrange: rebuild the inputs recorded in the report (values were redacted).",
            f"    with pytest.raises({exc.type}):",
            f"        ...  # call {frame.function if frame else 'the failing function'} with those inputs",
            "    # After the fix, change this test to assert the correct behaviour instead.",
            "```",
        ]
    )


def triage_report(data: dict[str, Any]) -> str:
    groups: list[dict[str, Any]] = []
    if "groups" in data:
        groups = data["groups"]
    elif "case_file" in data or "incident_id" in data:
        cf = data.get("case_file", data)
        groups = [
            {
                "fingerprint": f"I-{cf.get('incident_id')}",
                "count": cf.get("occurrence_count", 1),
                "type": (cf.get("exception") or {}).get("type", "?"),
                "message": cf.get("title", ""),
                "sample": {"exception": cf.get("exception")},
            }
        ]
    elif "issues" in data:
        groups = data["issues"]
    out = ["# Triage note", "", f"Report version: {data.get('version', 'unknown')}", ""]
    if not groups:
        return "\n".join([*out, "No errors in this report."])
    out += [
        "## Groups (duplicates merged by fingerprint)",
        "",
        "| Group | Count | Error |",
        "|---|---|---|",
    ]
    for g in groups:
        out.append(
            f"| `{g.get('fingerprint')}` | {g.get('count', 1)} | {g.get('type')}: {str(g.get('message', ''))[:80]} |"
        )
    for g in groups[:5]:
        sample = g.get("sample", g)
        exc = _exc_from(sample)
        out += ["", f"## {g.get('fingerprint')}", ""]
        if exc is None:
            out.append(
                "Traceback could not be parsed. Unknown location. Ask the reporter for `faultsage self-report --export`."
            )
            continue
        frames = [f for f in exc.frames if f.is_project] or exc.frames
        if frames:
            f = frames[-1]
            out.append(
                f"Possible location: `{f.file_path}:{f.line}` in `{f.function}` (innermost project frame)."
            )
        out.append(
            "Certainty: Possible. Based on the traceback only; reproduce before trusting it."
        )
        out += ["", "Frames (outermost first):", ""]
        out += [
            f"- `{fr.file_path}:{fr.line}` {fr.function}" + (" (project)" if fr.is_project else "")
            for fr in exc.frames[-8:]
        ]
        out += [
            "",
            "Draft failing test:",
            "",
            _test_draft(str(g.get("fingerprint", "bug"))[:24], exc),
        ]
    out += [
        "",
        "## Next steps",
        "",
        "1. Give this note to your coding agent with the triage prompt in docs/PROMPTS.md.",
        "2. The agent turns the draft into a real failing test, then proposes the smallest fix in a PR.",
        "3. CI runs. You review and merge. No auto-merge.",
    ]
    return "\n".join(out) + "\n"

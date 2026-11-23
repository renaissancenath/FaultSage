"""Triage agent for production errors (RELEASE_AND_OPERATIONS.md section 5, step 2).

Deterministic and free: it uses the FaultSage traceback analysis on the captured frames only
(no source code reaches the cloud), groups duplicates by fingerprint, ranks the likely location,
labels certainty honestly, drafts a failing regression test from the captured data, and writes a
fix request an engineer (or their coding agent) turns into a pull request. A human reviews every
fix; nothing here changes code.
"""

from __future__ import annotations

import urllib.parse
from collections import Counter
from typing import Any

from faultsage.analysis.engine import Snapshot, analyse
from faultsage.models.core import ExceptionInfo
from faultsage.triage import _test_draft

PROMPT = """## Context
FaultSage Cloud captured this production error (redacted). Project: {project}. Issue: {issue_ref}.
Environment: {environment}. Release: {release}. Seen {count} time(s) since {first_seen}.

{error}

Likely location ({certainty}): {location}

## Task
Find the most likely cause, write a failing test that reproduces it from the captured data, then
propose the smallest fix.

## Constraints
No behaviour change outside the bug. No new dependencies. Follow AGENTS.md.

## Expected output
Root cause with evidence, the failing test, the fix, all checks passing, a PR for human review.
"""


def fingerprint_for(exc: ExceptionInfo) -> str:
    from faultsage.daemon.grouping import signature

    return signature(exc, exc.type)


def triage(
    issue: dict[str, Any], events: list[dict[str, Any]], project: dict[str, Any]
) -> dict[str, Any]:
    payloads = [e["payload"] for e in events]
    exc_data = next((p.get("exception") for p in payloads if p.get("exception")), None)
    exc = ExceptionInfo.model_validate(exc_data) if exc_data else None
    releases = Counter(p.get("release", "") for p in payloads if p.get("release"))
    envs = Counter(p.get("environment", "") for p in payloads if p.get("environment"))
    hosts = Counter(p.get("server_name", "") for p in payloads if p.get("server_name"))
    result: dict[str, Any] = {
        "version": 1,
        "fingerprint": issue["fingerprint"],
        "count": issue["event_count"],
        "releases": dict(releases.most_common(5)),
        "environments": dict(envs.most_common(5)),
        "hosts": len(hosts),
    }
    if exc is None:
        result.update(
            {
                "certainty": "unknown",
                "location": None,
                "hypotheses": [],
                "summary": "No structured traceback was captured. Unknown location.",
                "missing": ["traceback frames"],
            }
        )
        return result
    snap = Snapshot(read_file=lambda _p: None, python_files=[])
    analysis = analyse(exc, [], snap)
    hyps = [
        {
            "rank": h.rank,
            "certainty": h.certainty,
            "claim": h.claim,
            "location": h.location.model_dump() if h.location else None,
            "evidence": [e.model_dump() for e in h.evidence],
        }
        for h in analysis.hypotheses[:5]
    ]
    top = analysis.hypotheses[0] if analysis.hypotheses else None
    loc = top.location if top else None
    # Source never reaches the cloud, so the line comes from the captured traceback itself.
    frame = exc.innermost_project_frame()
    if frame is not None and frame.line:
        from faultsage.models.core import Location

        loc = Location(
            file_path=frame.file_path,
            line=frame.line,
            function=frame.function,
            excerpt=[(frame.line, frame.code)] if frame.code else None,
            available=True,
        )
    loc_text = (
        f"{loc.file_path}:{loc.line} in {loc.function or '?'}" if loc and loc.line else "unknown"
    )
    first_release = min(releases) if releases else ""
    summary = [f"{exc.type}: {exc.message.splitlines()[0][:160] if exc.message else ''}"]
    if len(releases) == 1 and first_release:
        summary.append(f"Only seen in release {first_release}: likely introduced there.")
    result.update(
        {
            "certainty": top.certainty if top else "unknown",
            "location": loc.model_dump() if loc else None,
            "hypotheses": hyps,
            "summary": " ".join(summary),
            "missing": ["source code (stays on your machine)", "git history", "coverage"],
            "draft_test": _test_draft(f"issue_{issue['id']}", exc),
        }
    )
    error_block = "\n".join(
        ["```", f"{exc.type}: {exc.message[:500]}"]
        + [f'  File "{f.file_path}", line {f.line}, in {f.function}' for f in exc.frames[-12:]]
        + ["```"]
    )
    result["agent_prompt"] = PROMPT.format(
        project=project.get("name"),
        issue_ref=f"FS-{issue['id']}",
        environment=issue.get("environment") or "-",
        release=issue.get("last_release") or "-",
        count=issue["event_count"],
        first_seen=issue["first_seen_at"],
        error=error_block,
        certainty=(top.certainty.capitalize() if top else "Unknown"),
        location=loc_text,
    )
    repo = (project.get("repo_url") or "").rstrip("/")
    if repo.startswith("https://github.com/"):
        body = (
            f"Production error captured by FaultSage (FS-{issue['id']}).\n\n{result['summary']}\n\n"
            f"{error_block}\n\n### Draft regression test\n\n{result['draft_test']}\n\n"
            f"### Prompt for the coding agent\n\n{result['agent_prompt']}"
        )
        params = urllib.parse.urlencode(
            {
                "title": f"[prod] {issue['title'][:120]}",
                "body": body[:6000],
                "labels": "bug,prod-bug",
            }
        )
        result["github_issue_url"] = f"{repo}/issues/new?{params}"
    return result

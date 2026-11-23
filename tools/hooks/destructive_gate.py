"""Coding-agent pre-tool hook: every destructive call needs a human "yes", every time.

AGENTS.md section 5 and SR-28. Reads the tool call as JSON on stdin. For a destructive shell
command (dropping tables, destructive migrations, deleting files outside .faultsage, force pushes,
history rewrites, hard resets) it answers "ask", so the engineer must approve that exact call.
Approvals are per call by construction: the hook runs again on the next call and asks again.
Edits that add DROP/DELETE SQL to a migration that is not named *_destructive.sql are denied.
"""

from __future__ import annotations

import json
import re
import sys

DESTRUCTIVE_SHELL = [
    (
        re.compile(
            r"\b(DROP\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW)|TRUNCATE|DELETE\s+FROM|ALTER\s+TABLE\s+\S+\s+(DROP|RENAME))\b",
            re.I,
        ),
        "runs destructive SQL",
    ),
    (re.compile(r"\bdb\s+migrate\b.*--approve\b"), "applies a destructive database migration"),
    (re.compile(r"\bpurge\b.*(--all)?"), "purges FaultSage data"),
    (re.compile(r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+"), "deletes files recursively or by force"),
    (
        re.compile(r"\bgit\s+push\b.*(--force|-f\b|--force-with-lease|--delete|:)"),
        "force-pushes or deletes a remote branch",
    ),
    (
        re.compile(
            r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f|branch\s+-D|rebase\b|filter-branch|filter-repo)"
        ),
        "rewrites or discards git history or work",
    ),
    (re.compile(r"\bgit\s+push\b"), "pushes to a remote"),
    (re.compile(r"\b(dropdb|pg_restore\s+.*--clean)\b"), "drops or overwrites a database"),
    (re.compile(r"\bdb\s+restore\b"), "replaces the whole database with a backup"),
    (
        re.compile(r"\bdocker\s+(volume\s+rm|system\s+prune|compose\s+down\s+.*-v)"),
        "deletes container data",
    ),
]
DESTRUCTIVE_SQL = re.compile(
    r"\b(DROP\s+(TABLE|INDEX|VIEW|COLUMN)|DELETE\s+FROM|TRUNCATE|RENAME\s+TO)\b", re.I
)


def decide(event: dict) -> dict | None:
    tool = event.get("tool_name", "")
    inp = event.get("tool_input", {}) or {}
    if tool == "Bash":
        cmd = str(inp.get("command", ""))
        for rx, what in DESTRUCTIVE_SHELL:
            if rx.search(cmd):
                return {
                    "permissionDecision": "ask",
                    "permissionDecisionReason": f"FaultSage approval gate: this command {what}. "
                    "Approve only this exact call; the next destructive call will ask again (SR-28).",
                }
    if tool in ("Write", "Edit", "MultiEdit"):
        path = str(inp.get("file_path", ""))
        text = str(inp.get("content", "")) + str(inp.get("new_string", ""))
        if (
            "/migrations/" in path.replace("\\", "/")
            and path.endswith(".sql")
            and DESTRUCTIVE_SQL.search(text)
            and not path.endswith("_destructive.sql")
        ):
            return {
                "permissionDecision": "deny",
                "permissionDecisionReason": "Destructive SQL must go in a migration named NNNN_name_destructive.sql "
                "so the runtime approval gate applies (DATABASE.md section 4).",
            }
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    verdict = decide(event)
    if verdict:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", **verdict}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

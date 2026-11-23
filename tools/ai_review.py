"""Review a pull request with any chat-completions API, using the review prompt in docs/PROMPTS.md.

Called by .github/workflows/ai-review.yml. Reads the diff between two commits, sends it with the
prompt, and writes the reply to a Markdown file that the workflow posts as a PR comment. It never
pushes, approves or merges.

Environment: AI_REVIEW_API_KEY, AI_REVIEW_BASE_URL (an OpenAI-compatible endpoint, for example
https://<provider>/v1), AI_REVIEW_MODEL, PR_NUMBER, BASE_SHA, HEAD_SHA.

Usage: python tools/ai_review.py OUTPUT.md
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
MAX_DIFF = 60_000


def review_prompt() -> str:
    text = (ROOT / "docs" / "PROMPTS.md").read_text(encoding="utf-8")
    section = text.split("## Review prompt (agentic PR review)", 1)[1]
    block = re.search(r"```markdown\n(.*?)```", section, re.S)
    if block is None:
        raise SystemExit("Review prompt not found in docs/PROMPTS.md")
    return block.group(1).replace("<n>", os.environ.get("PR_NUMBER", "?"))


def pr_diff(base: str, head: str) -> str:
    out = subprocess.run(
        ["git", "diff", "--no-color", f"{base}...{head}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout
    if len(out) > MAX_DIFF:
        out = out[:MAX_DIFF] + f"\n[diff cut at {MAX_DIFF} characters]\n"
    return out


def main() -> int:
    out_file = Path(sys.argv[1])
    diff = pr_diff(os.environ["BASE_SHA"], os.environ["HEAD_SHA"])
    if not diff.strip():
        out_file.write_text("No code changes to review.\n", encoding="utf-8")
        return 0
    resp = httpx.post(
        os.environ["AI_REVIEW_BASE_URL"].rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['AI_REVIEW_API_KEY']}"},
        json={
            "model": os.environ["AI_REVIEW_MODEL"],
            "messages": [
                {"role": "system", "content": review_prompt()},
                {"role": "user", "content": f"Diff of this pull request:\n\n```diff\n{diff}```"},
            ],
        },
        timeout=300,
    )
    resp.raise_for_status()
    reply = resp.json()["choices"][0]["message"]["content"].strip()
    out_file.write_text(
        f"### Automated review\n\n{reply}\n\n"
        "_Suggestions only. A person reviews and merges every pull request._\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

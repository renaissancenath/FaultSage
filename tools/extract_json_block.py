"""Print the first ```json fenced block (or the whole body if it is JSON) from $BODY.

Used by the triage workflow. The issue body is untrusted: it is parsed as JSON and re-serialised,
never executed. Exit code 1 if there is no valid JSON.
"""

from __future__ import annotations

import json
import os
import re
import sys


def main() -> int:
    body = os.environ.get("BODY", "")[:500_000]
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", body, re.S)
    text = m.group(1) if m else body
    try:
        data = json.loads(text)
    except ValueError:
        print("No JSON export found in the issue body.", file=sys.stderr)
        return 1
    print(json.dumps(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())

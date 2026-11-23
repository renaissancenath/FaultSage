"""Job-summary sections for the Friday release check.

python tools/release_report.py migrations   pending destructive migrations (local and cloud)
python tools/release_report.py checklist    the launch checklist as Markdown
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from faultsage.migration_gate import destructive_statements, discover  # noqa: E402


def migrations() -> str:
    out = ["## Destructive migrations in the code base", ""]
    found = False
    for label, folder in (
        ("local", ROOT / "src/faultsage/storage/migrations"),
        ("cloud", ROOT / "src/faultsage/cloud/storage/migrations"),
    ):
        for m in discover(folder):
            if m.destructive:
                found = True
                out.append(
                    f"- {label} {m.version:04d} {m.name}: "
                    + "; ".join(destructive_statements(m.sql))
                )
    if not found:
        out.append("None. Nothing needs a destructive approval in this release.")
    else:
        out.append("")
        out.append(
            "Each needs a named human approval per environment: "
            "`faultsage-cloud db migrate --approve N --env production --approved-by NAME`."
        )
    return "\n".join(out) + "\n"


def checklist() -> str:
    return (ROOT / "docs/security/05_LAUNCH-CHECKLIST.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "checklist"
    print(migrations() if what == "migrations" else checklist())

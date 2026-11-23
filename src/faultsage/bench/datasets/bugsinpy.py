"""BugsInPy adapter (DATASETS.md). Reads the official repository layout:

projects/<project>/project.info             github_url
projects/<project>/bugs/<id>/bug.info       python_version, buggy_commit_id, fixed_commit_id, test_file
projects/<project>/bugs/<id>/bug_patch.txt  the developer's fix (ground truth)
projects/<project>/bugs/<id>/run_test.sh    the failing test command(s)
projects/<project>/bugs/<id>/requirements.txt  pinned dependencies (often UTF-16)
projects/<project>/bugs/<id>/setup.sh       extra setup commands
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO_URL = "https://github.com/soarsmu/BugsInPy.git"
_KV = re.compile(r'^(\w+)="?(.*?)"?\s*$')


@dataclass(slots=True)
class Case:
    project: str
    bug_id: str
    github_url: str
    buggy_commit: str
    fixed_commit: str
    test_files: list[str]
    test_commands: list[str]
    python_version: str = "3.8"
    requirements: str = ""
    setup: str = ""
    truth_files: list[str] = field(default_factory=list)
    truth_hunks: dict[str, list[tuple[int, int]]] = field(default_factory=dict)

    @property
    def case_id(self) -> str:
        return f"{self.project}-{self.bug_id}"


def read_text_any(path: Path) -> str:
    """BugsInPy mixes UTF-8 and UTF-16 (with BOM) files."""
    if not path.exists():
        return ""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace")


UNINSTALLABLE = {
    "pywin32",
    "pypiwin32",
    "pywin32-ctypes",
    "pywinpty",
    "pkg-resources",
    "pkg_resources",
}


def clean_requirements(text: str, github_url: str) -> str:
    """Drop the pip-freeze line that installs the project itself from git: the harness provides
    the project source from its own buggy and fixed checkouts."""
    slug = github_url.rstrip("/").lower().split("github.com/")[-1]
    keep = []
    for ln in text.splitlines():
        name = ln.split("==")[0].strip().lower()
        if "git+" in ln and slug and slug in ln.lower():
            continue
        # pip-freeze artifacts that no Linux machine can install: Windows-only packages, and
        # "pkg-resources==0.0.0" from a bug in Debian/Ubuntu's pip.
        if name in UNINSTALLABLE:
            continue
        keep.append(ln)
    return "\n".join(keep) + "\n"


def _info(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in read_text_any(path).splitlines():
        m = _KV.match(line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or any(p in ("test", "tests", "testing") for p in parts[:-1])
    )


def truth_from_patch(patch: str) -> tuple[list[str], dict[str, list[tuple[int, int]]]]:
    files: list[str] = []
    hunks: dict[str, list[tuple[int, int]]] = {}
    current = None
    for line in patch.splitlines():
        if line.startswith("--- a/"):
            current = line[6:].strip()
            if current.endswith(".py") and not is_test_path(current):
                files.append(current)
                hunks[current] = []
            else:
                current = None
        elif line.startswith("@@") and current:
            m = re.match(r"^@@ -(\d+)(?:,(\d+))?", line)
            if m:
                start = int(m.group(1))
                hunks[current].append((start, start + int(m.group(2) or 1) - 1))
    return files, hunks


def fetch(data_dir: Path) -> str:
    """Clone or update BugsInPy; return the commit recorded in the run record (FR-31)."""
    dest = data_dir / "BugsInPy"
    if not dest.exists():
        subprocess.run(
            ["git", "clone", "--depth", "1", REPO_URL, str(dest)], check=True, timeout=600
        )
    head = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()
    return f"git:{head}"


def load_cases(data_dir: Path, projects: list[str] | None = None) -> list[Case]:
    base = data_dir / "BugsInPy" / "projects"
    cases: list[Case] = []
    if not base.exists():
        return cases
    for proj_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        if projects and proj_dir.name not in projects:
            continue
        url = _info(proj_dir / "project.info").get("github_url", "")
        bugs = sorted(
            (proj_dir / "bugs").iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0
        )
        for bug_dir in bugs:
            info = _info(bug_dir / "bug.info")
            if not info.get("buggy_commit_id"):
                continue
            files, hunks = truth_from_patch(read_text_any(bug_dir / "bug_patch.txt"))
            cmds = [
                ln.strip()
                for ln in read_text_any(bug_dir / "run_test.sh").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")
            ]
            cases.append(
                Case(
                    project=proj_dir.name,
                    bug_id=bug_dir.name,
                    github_url=url,
                    buggy_commit=info["buggy_commit_id"],
                    fixed_commit=info.get("fixed_commit_id", ""),
                    test_files=[t for t in info.get("test_file", "").split(";") if t],
                    test_commands=cmds,
                    python_version=info.get("python_version", "3.8"),
                    requirements=clean_requirements(
                        read_text_any(bug_dir / "requirements.txt"), url
                    ),
                    setup=read_text_any(bug_dir / "setup.sh"),
                    truth_files=files,
                    truth_hunks=hunks,
                )
            )
    return cases

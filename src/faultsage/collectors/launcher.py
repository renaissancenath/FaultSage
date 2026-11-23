"""runpy launcher with an exception hook (FR-7).

Usage (internal): python -m faultsage.collectors.launcher <spool_dir> <root> script.py|-m module [args]
Writes the structured uncaught exception to a side file the run wrapper reads.
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

from faultsage.collectors.frames import exception_info


def main() -> int:
    if len(sys.argv) < 4:
        print("launcher: missing arguments", file=sys.stderr)
        return 2
    out_file = Path(sys.argv[1])
    root = Path(sys.argv[2])
    rest = sys.argv[3:]
    try:
        if rest[0] == "-m":
            sys.argv = [rest[1], *rest[2:]]
            runpy.run_module(rest[1], run_name="__main__", alter_sys=True)
        else:
            sys.argv = rest
            sys.path.insert(0, str(Path(rest[0]).resolve().parent))
            runpy.run_path(rest[0], run_name="__main__")
    except SystemExit:
        raise
    except BaseException as exc:
        try:
            info = exception_info(root, exc).model_dump(mode="json")
            out_file.write_text(json.dumps(info), encoding="utf-8")
        except Exception:  # noqa: S110  # nosec B110
            pass  # recording must not hide the user's real error
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())

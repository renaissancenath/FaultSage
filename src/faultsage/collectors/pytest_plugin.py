"""Pytest plugin (FR-5, FR-6). Writes one test_result event per report to the spool.

Must never block or fail a test run: every internal error is swallowed and logged to
.faultsage/logs/plugin.log.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from faultsage.collectors.frames import exception_info
from faultsage.collectors.spool import SpoolWriter
from faultsage.redact import redact

_STATE: dict[str, Any] = {"writer": None, "session_id": "", "excinfo": {}, "cov": False}
_log = logging.getLogger("faultsage.plugin")


def _setup_logging(log_dir: Path) -> None:
    if _log.handlers:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "plugin.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _log.addHandler(handler)
    _log.propagate = False


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("faultsage")
    group.addoption(
        "--no-faultsage", action="store_true", default=False, help="Disable FaultSage recording."
    )


def pytest_configure(config: pytest.Config) -> None:
    # Broad catch is deliberate: the plugin must never break the user's test run (FR-6).
    try:
        if config.getoption("--no-faultsage", default=False):
            return
        from faultsage.config.loader import load, locate

        paths = locate(Path(str(config.rootpath)))
        if not paths.config.exists():
            return
        cfg = load(paths)
        if not cfg.signals.pytest:
            return
        _setup_logging(paths.logs)
        _STATE["writer"] = SpoolWriter(paths.spool, "pytest_plugin", paths.root)
        _STATE["session_id"] = uuid.uuid4().hex
        _STATE["cov"] = bool(getattr(config.option, "cov_context", None))
    except Exception:
        _STATE["writer"] = None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, Any, Any]:
    report = yield
    try:
        if _STATE["writer"] is not None and call.excinfo is not None:
            _STATE["excinfo"][(item.nodeid, call.when)] = call.excinfo.value
    except Exception:
        _log.exception("makereport capture failed")
    return report


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    writer: SpoolWriter | None = _STATE["writer"]
    if writer is None:
        return
    try:
        if report.when != "call" and report.outcome == "passed":
            return  # only call-phase passes are interesting; setup/teardown errors are
        exc = _STATE["excinfo"].pop((report.nodeid, report.when), None)
        outcome: str = report.outcome
        if report.failed and report.when != "call":
            outcome = "error"
        info = None
        if exc is not None and report.failed:
            info = exception_info(Path(writer.project_root), exc).model_dump(mode="json")
        longrepr = redact(str(report.longrepr))[:20_000] if report.failed else ""
        writer.write(
            "test_result",
            {
                "node_id": report.nodeid,
                "phase": report.when,
                "outcome": outcome,
                "duration_s": round(float(report.duration), 4),
                "exception": info,
                "longrepr_text": longrepr,
                "coverage_context": bool(_STATE["cov"]),
                "session_id": _STATE["session_id"],
            },
        )
    except Exception:
        _log.exception("logreport failed for %s", getattr(report, "nodeid", "?"))

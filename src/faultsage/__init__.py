"""FaultSage: finds the line that broke your Python project and checks your fix."""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"
__all__ = ["__version__", "checkpoint"]


def checkpoint(obj: Any, step: str) -> None:
    """Record the schema (type, shape, column names and dtypes) of ``obj`` at pipeline ``step``.

    Never records values (FR-11). Safe to call when FaultSage is not configured: it does nothing.
    """
    from faultsage.collectors.checkpoint import record_checkpoint

    record_checkpoint(obj, step)

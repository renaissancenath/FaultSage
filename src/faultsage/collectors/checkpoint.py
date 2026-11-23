"""Pipeline checkpoints (FR-11): type, shape and column names/dtypes only. Never values."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from faultsage.collectors.spool import SpoolWriter

_writer: SpoolWriter | None = None
_log = logging.getLogger("faultsage.checkpoint")


def describe(obj: Any) -> dict[str, Any]:
    kind = type(obj).__module__.split(".")[0] + "." + type(obj).__qualname__
    shape: list[int] | None = None
    columns: list[dict[str, str]] = []
    if hasattr(obj, "columns") and hasattr(obj, "dtypes"):
        # pandas / polars DataFrame
        try:
            dtypes = obj.dtypes
            if hasattr(dtypes, "items"):  # pandas Series of dtypes
                columns = [{"name": str(n), "dtype": str(t)} for n, t in dtypes.items()]
            else:  # polars list of dtypes
                columns = [
                    {"name": str(n), "dtype": str(t)}
                    for n, t in zip(obj.columns, dtypes, strict=False)
                ]
        except (AttributeError, TypeError):
            columns = [{"name": str(n), "dtype": "unknown"} for n in obj.columns]
    elif isinstance(obj, dict):
        columns = [{"name": str(k), "dtype": type(v).__name__} for k, v in obj.items()]
        shape = [len(obj)]
    if hasattr(obj, "shape"):
        try:
            shape = [int(x) for x in obj.shape]
        except (TypeError, ValueError):
            shape = None
    elif shape is None and hasattr(obj, "__len__"):
        try:
            shape = [len(obj)]
        except TypeError:
            shape = None
    return {"object_type": kind, "shape": shape, "columns": columns[:2000]}


def record_checkpoint(obj: Any, step: str) -> None:
    global _writer
    try:
        if _writer is None:
            from faultsage.config.loader import locate

            paths = locate(Path.cwd())
            if not paths.config.exists():
                return
            _writer = SpoolWriter(paths.spool, "checkpoint", paths.root)
        _writer.write("checkpoint", {"step": step, **describe(obj)})
    except Exception:
        _log.debug("checkpoint failed", exc_info=True)

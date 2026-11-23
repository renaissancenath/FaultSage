"""Secret redaction applied to every text field before storage, display or export (SR-16).

Regexes are linear-time (no nested quantifiers) and inputs are capped to avoid ReDoS.
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter

MAX_INPUT = 200_000
SECRET_KEY_NAMES = r"pass(?:word|wd)?|pwd|secret|token|api[_-]?key|auth|credential|cookie|session"  # noqa: S105  names to look for
_SECRET_NAME_RX = re.compile(rf"(?:{SECRET_KEY_NAMES})", re.I)

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----[\s\S]{0,8000}?-----END [A-Z ]{0,40}PRIVATE KEY-----"
        ),
    ),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "github_token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b"),
    ),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,200}\b")),
    ("faultsage_key", re.compile(r"\bfsk_[A-Za-z0-9_-]{20,200}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer", re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}")),
]
# key=value / key: value / "key": "value" where key looks secret
_KV = re.compile(
    rf"""(?ix)
    (["']?[A-Za-z0-9_.-]{{0,40}}(?:{SECRET_KEY_NAMES})[A-Za-z0-9_.-]{{0,40}}["']?)
    (\s{{0,3}}[:=]\s{{0,3}})
    ("[^"\n]{{1,500}}"|'[^'\n]{{1,500}}'|[^\s,;&"'}}\]]{{1,500}})
    """
)
_HIGH_ENTROPY_ASSIGN = re.compile(r"([=:]\s{0,3}[\"']?)([A-Za-z0-9+/_=-]{32,512})")


def _entropy(s: str) -> float:
    counts = Counter(s)
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _secret_env_values() -> list[str]:
    values = []
    for name, value in os.environ.items():
        if _SECRET_NAME_RX.search(name) and len(value) >= 6:
            values.append(value)
    # Longest first so overlapping values redact fully.
    return sorted(set(values), key=len, reverse=True)


def redact(text: str | None, *, max_len: int = MAX_INPUT) -> str:
    """Return ``text`` with secrets replaced by ``[redacted:<kind>]``. ``None`` becomes ``""``."""
    if not text:
        return ""
    out = text[:max_len]
    for value in _secret_env_values():
        if value in out:
            out = out.replace(value, "[redacted:env]")
    for kind, rx in _PATTERNS:
        if kind == "bearer":
            out = rx.sub(lambda m: f"{m.group(1)} [redacted:bearer]", out)
        else:
            out = rx.sub(f"[redacted:{kind}]", out)

    def _kv(m: re.Match[str]) -> str:
        value = m.group(3)
        if value.startswith("[redacted:"):
            return m.group(0)
        quote = value[0] if value[0] in "\"'" else ""
        return f"{m.group(1)}{m.group(2)}{quote}[redacted:secret]{quote}"

    out = _KV.sub(_kv, out)

    def _he(m: re.Match[str]) -> str:
        token = m.group(2)
        if (
            _entropy(token) >= 4.0
            and any(c.isdigit() for c in token)
            and any(c.isalpha() for c in token)
        ):
            return f"{m.group(1)}[redacted:high_entropy]"
        return m.group(0)

    return _HIGH_ENTROPY_ASSIGN.sub(_he, out)


def redact_obj(value: object) -> object:
    """Recursively redact all strings inside lists and dicts."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_obj(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_obj(v) for v in value)
    if isinstance(value, dict):
        return {k: redact_obj(v) for k, v in value.items()}
    return value


# Fields of a case file that hold the user's source code: lines around a location, and patches.
SOURCE_FIELDS = frozenset({"excerpt", "patch_diff"})


def strip_source(value: object) -> object:
    """Remove source code from a case file before it leaves the machine (D-030). Tracebacks keep
    their one-line frames, like any error report; code excerpts and patch diffs are dropped."""
    if isinstance(value, list):
        return [strip_source(v) for v in value]
    if isinstance(value, dict):
        return {k: (None if k in SOURCE_FIELDS else strip_source(v)) for k, v in value.items()}
    return value

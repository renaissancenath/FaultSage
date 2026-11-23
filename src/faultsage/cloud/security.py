"""Cloud auth primitives (02_LOGIN-RULES.md section 4, D-015).

- Passwords: Argon2id, memory cost 64 MiB, min length 12, checked against a local list of common
  breached passwords, no composition rules.
- Lockout: exponential backoff after 5 failures; generic error messages.
- Sessions: 256-bit random ids stored hashed, rotated on login, Secure+HttpOnly cookies over HTTPS.
- CSRF: per-session token (double submit) required on state-changing requests.
- API keys: ``fsk_`` + 32 random bytes, stored as SHA-256, shown once.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
MIN_PASSWORD = 12
MAX_PASSWORD = 256
LOCK_AFTER = 5
SESSION_DAYS = 14
_BREACHED_FILE = Path(__file__).with_name("breached_passwords.txt")
_breached: set[str] | None = None
# A dummy hash so unknown emails take the same time as wrong passwords.
_DUMMY = _ph.hash(secrets.token_urlsafe(16))


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def breached() -> set[str]:
    global _breached
    if _breached is None:
        _breached = set()
        if _BREACHED_FILE.exists():
            _breached = {
                ln.strip().lower()
                for ln in _BREACHED_FILE.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")
            }
    return _breached


def password_problem(password: str, email: str = "") -> str | None:
    if len(password) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if len(password) > MAX_PASSWORD:
        return f"Use at most {MAX_PASSWORD} characters."
    low = password.lower()
    if low in breached():
        return "This password appears in public breach lists. Choose another."
    if email and low == email.lower():
        return "Do not use your email address as the password."
    if len(set(password)) < 4:
        return "This password is too repetitive."
    return None


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored: str | None, password: str) -> bool:
    try:
        return _ph.verify(stored or _DUMMY, password) and stored is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return _ph.check_needs_rehash(stored)
    except InvalidHashError:
        return True


def lockout_until(failed: int) -> datetime | None:
    """Exponential backoff after 5 failures: 30 s, 60 s, 120 s ... capped at 1 h."""
    if failed < LOCK_AFTER:
        return None
    seconds = min(30 * 2 ** (failed - LOCK_AFTER), 3600)
    return datetime.now(UTC) + timedelta(seconds=seconds)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_api_key() -> tuple[str, str, str]:
    """Return (raw key shown once, prefix for display, sha256 for storage)."""
    raw = "fsk_" + secrets.token_urlsafe(32)
    return raw, raw[:12], sha256(raw)


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


class RateLimiter:
    """In-process sliding window. Good for a single instance; behind several instances use a
    shared store (documented in RELEASE_AND_OPERATIONS.md)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: float) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            while dq and now - dq[0] > window_s:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            if len(self._hits) > 50_000:  # bound memory
                for k in list(self._hits)[:10_000]:
                    del self._hits[k]
            return True

    def wait_seconds(self, key: str, window_s: float) -> int:
        """Seconds until the oldest counted request leaves the window."""
        with self._lock:
            dq = self._hits.get(key)
            if not dq:
                return 0
            return max(1, int(window_s - (time.monotonic() - dq[0])) + 1)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()

"""Local dashboard session auth (02_LOGIN-RULES.md section 2, LR-1 to LR-7, SR-2 to SR-4)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field

SESSION_COOKIE = "fs_session"
IDLE_TIMEOUT_S = 12 * 3600  # LR-2
MAX_SESSIONS = 5  # LR-3
RATE_WINDOW_S = 60
RATE_MAX = 10  # LR-4
LOCKOUT_S = 60


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class SessionStore:
    """In memory only. Never written to the DB (LR-1). Lost when the daemon stops (LR-2)."""

    _token_hash: str | None = None
    _sessions: OrderedDict[str, float] = field(default_factory=OrderedDict)
    _attempts: deque[float] = field(default_factory=deque)
    _locked_until: float = 0.0
    failed_count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def new_token(self) -> str:
        """Issue a one-time token (256 bits). Only its hash is kept."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._token_hash = _h(token)
        return token

    def exchange(self, token: str, now: float | None = None) -> str | None:
        """Exchange the one-time token for a session id, or None. Rate limited (LR-4)."""
        t = now if now is not None else time.monotonic()
        with self._lock:
            if t < self._locked_until:
                return None
            while self._attempts and t - self._attempts[0] > RATE_WINDOW_S:
                self._attempts.popleft()
            self._attempts.append(t)
            if len(self._attempts) > RATE_MAX:
                self._locked_until = t + LOCKOUT_S
                self._attempts.clear()
                self.failed_count += 1
                return None
            expected = self._token_hash
            if expected is None or not hmac.compare_digest(_h(token), expected):
                self.failed_count += 1
                return None
            self._token_hash = None  # one-time use (LR step 6)
            sid = secrets.token_urlsafe(32)
            self._sessions[_h(sid)] = t
            while len(self._sessions) > MAX_SESSIONS:
                self._sessions.popitem(last=False)
            return sid

    def valid(self, sid: str | None, now: float | None = None) -> bool:
        if not sid:
            return False
        t = now if now is not None else time.monotonic()
        key = _h(sid)
        with self._lock:
            seen = self._sessions.get(key)
            if seen is None:
                return False
            if t - seen > IDLE_TIMEOUT_S:
                del self._sessions[key]
                return False
            self._sessions[key] = t
            self._sessions.move_to_end(key)
            return True

    def revoke_all(self) -> None:
        with self._lock:
            self._sessions.clear()
            self._token_hash = None


def allowed_hosts(port: int) -> set[str]:
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


def allowed_origins(port: int) -> set[str]:
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

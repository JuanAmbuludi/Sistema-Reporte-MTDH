"""Password hashing and a process-wide, thread-safe login throttle.

Passwords never enter the data pipeline or exports.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time

ITERATIONS = 600_000


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Utiliza una contraseña de al menos 12 caracteres.")
    salt = secrets.token_bytes(24)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return "$".join(("pbkdf2_sha256", str(ITERATIONS), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()))


def verify_password(password: str, encoded: str) -> bool:
    try:
        method, iterations, salt, expected = encoded.split("$")
        count = int(iterations)
        if method != "pbkdf2_sha256" or not 600_000 <= count <= 2_000_000:
            return False
        salt_bytes = base64.b64decode(salt, validate=True)
        expected_bytes = base64.b64decode(expected, validate=True)
        if len(salt_bytes) < 16 or len(expected_bytes) != 32:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, count)
        return hmac.compare_digest(actual, expected_bytes)
    except (ValueError, TypeError, AttributeError):
        return False


class LoginThrottle:
    """Five failed attempts lock an account for five minutes in this process.

    State spans browser sessions and is bounded. For multiple replicas, use an
    institutional identity provider or a shared rate-limit store.
    """
    def __init__(self, limit: int = 5, window: int = 300):
        self.limit = limit
        self.window = window
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.RLock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._attempts.get(key, []) if now - t < self.window]
        if recent:
            self._attempts[key] = recent
        else:
            self._attempts.pop(key, None)
        return recent

    def remaining(self, key: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            recent = self._recent(key, now)
            return max(1, int(self.window - (now - recent[0])) + 1) if len(recent) >= self.limit else 0

    def failure(self, key: str, now: float | None = None):
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._attempts) >= 10000:
                self._attempts = {k: [t for t in v if now - t < self.window] for k, v in self._attempts.items()}
                self._attempts = {k: v for k, v in self._attempts.items() if v}
                if len(self._attempts) >= 10000:
                    oldest = min(self._attempts, key=lambda k: self._attempts[k][-1])
                    self._attempts.pop(oldest)
            self._attempts[key] = (self._recent(key, now) + [now])[-self.limit:]

    def success(self, key: str):
        with self._lock:
            self._attempts.pop(key, None)

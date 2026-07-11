"""JWT session issuing/verification, password check, and a simple in-app
login rate limiter. See CLAUDE.md for the silent-redirect rule this
supports: any missing/invalid/expired token means a bare redirect to
/gc-admin/login, never an error message.
"""
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from flask import current_app

from database.db import query_one

COOKIE_NAME = "gc_session"

# In-memory only — resets on restart and isn't shared across Passenger
# worker processes. Acceptable for a single-admin personal site; documented
# as a known simplification in CLAUDE.md rather than pulling in Redis/etc.
_failed_attempts: dict[str, list[float]] = {}
MAX_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < LOCKOUT_WINDOW_SECONDS]
    _failed_attempts[ip] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def record_failed_attempt(ip: str) -> None:
    _failed_attempts.setdefault(ip, []).append(time.time())


def clear_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)


def verify_credentials(username: str, password: str) -> bool:
    if not username or not password:
        return False
    user = query_one("SELECT password_hash FROM admin_users WHERE username = %s", (username,))
    if not user:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8"))


def issue_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + timedelta(minutes=current_app.config["JWT_EXPIRY_MINUTES"]),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def verify_token(token: str):
    """Returns the decoded payload, or None for any missing/invalid/expired
    token — callers must never distinguish these cases to the user."""
    if not token:
        return None
    try:
        return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

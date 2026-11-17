"""JWT session issuing/verification, password check, and a simple in-app
login rate limiter. See CLAUDE.md for the silent-redirect rule this
supports: any missing/invalid/expired token means a bare redirect to
/gc-admin/login, never an error message.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from flask import current_app

from database.db import execute, query_one, utc_now

COOKIE_NAME = "gc_session"

# Failed logins live in the DB (login_attempts), not process memory:
# Passenger runs several worker processes and restarts them when idle, so an
# in-memory counter was per-process and reset itself. Two limits:
# per IP (stops one source guessing) and per username across all IPs (stops
# a botnet spreading guesses). The per-username limit is deliberately looser
# because anyone can trip it; it only blocks *new* sign-ins for the window,
# devices already signed in keep working.
MAX_ATTEMPTS = 5                # per IP
MAX_ATTEMPTS_PER_USERNAME = 20  # all IPs together
LOCKOUT_WINDOW_SECONDS = 15 * 60


def _window_start():
    return utc_now() - timedelta(seconds=LOCKOUT_WINDOW_SECONDS)


def is_rate_limited(ip: str, username: str = "") -> bool:
    since = _window_start()
    by_ip = query_one("SELECT COUNT(*) AS n FROM login_attempts WHERE ip = %s AND attempted_at > %s", (ip, since))
    if by_ip and by_ip["n"] >= MAX_ATTEMPTS:
        return True
    if username:
        by_user = query_one("SELECT COUNT(*) AS n FROM login_attempts WHERE username = %s AND attempted_at > %s",
                            (username[:100], since))
        if by_user and by_user["n"] >= MAX_ATTEMPTS_PER_USERNAME:
            return True
    return False


def record_failed_attempt(ip: str, username: str = "") -> None:
    now = utc_now()
    execute("INSERT INTO login_attempts (ip, username, attempted_at) VALUES (%s, %s, %s)",
            (ip[:45], (username or "")[:100], now))
    execute("DELETE FROM login_attempts WHERE attempted_at < %s", (now - timedelta(days=1),))


def clear_attempts(ip: str) -> None:
    execute("DELETE FROM login_attempts WHERE ip = %s", (ip[:45],))


def verify_credentials(username: str, password: str) -> bool:
    if not username or not password:
        return False
    user = query_one("SELECT password_hash FROM admin_users WHERE username = %s", (username,))
    if not user:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8"))


def token_lifetime(remember: bool = False) -> timedelta:
    if remember:
        return timedelta(days=current_app.config["REMEMBER_DEVICE_DAYS"])
    return timedelta(minutes=current_app.config["JWT_EXPIRY_MINUTES"])


def issue_token(username: str, remember: bool = False) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + token_lifetime(remember),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def _decode(token: str):
    if not token:
        return None
    try:
        return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"],
                          options={"require": ["exp", "iat", "sub"]})
    except jwt.PyJWTError:
        return None


def verify_token(token: str):
    """Returns the decoded session payload, or None for any missing/invalid/
    expired token — callers must never distinguish these cases to the user.
    Tokens with a "purpose" (the half-way MFA token) are never a session."""
    payload = _decode(token)
    if payload is None or "purpose" in payload:
        return None
    return payload


# Between a correct password and the authenticator code: proves the password
# step only, for 5 minutes, and can't be used as a session (verify_token).
PENDING_COOKIE = "gc_mfa"
PENDING_MINUTES = 5


def issue_pending_token(username: str, remember: bool) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "iat": now, "exp": now + timedelta(minutes=PENDING_MINUTES),
               "purpose": "mfa", "remember": bool(remember)}
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def verify_pending_token(token: str):
    payload = _decode(token)
    if payload is None or payload.get("purpose") != "mfa":
        return None
    return payload

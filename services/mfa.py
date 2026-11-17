"""Authenticator-app sign-in (TOTP) with trusted devices and recovery codes.

Glad asked to be asked for a code only on a device the site hasn't seen
before, so a passing code (or a recovery code) makes the browser a trusted
device: a random token in the HttpOnly gc_device cookie, stored here only
as a SHA-256 hash, valid for a year from its last use. Devices that were
already signed in before MFA was switched on are trusted automatically on
their next visit (blueprints/admin/mfa.py::session_state). Removing a device
from the list signs it out.
"""
import hashlib
import secrets
from datetime import timedelta

from database.db import execute, query, query_one, transaction, utc_now
from services import totp

DEVICE_COOKIE = "gc_device"
DEVICE_DAYS = 365
RECOVERY_CODE_COUNT = 10


def _hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _user(username):
    return query_one(
        "SELECT id, username, totp_secret, totp_pending_secret, totp_enabled_at, totp_last_counter "
        "FROM admin_users WHERE username = %s", (username,))


def enabled_at(username):
    """When MFA was switched on for this user, or None if it's off."""
    user = _user(username)
    return user["totp_enabled_at"] if user and user["totp_secret"] else None


def any_enabled() -> bool:
    return query_one("SELECT 1 AS on_ FROM admin_users WHERE totp_secret IS NOT NULL LIMIT 1") is not None


# --- setting it up --------------------------------------------------------------

def pending_secret(username) -> str:
    """The not-yet-confirmed secret shown as a QR code; created on first view
    and kept until confirmed, so reloading the page doesn't change the QR."""
    user = _user(username)
    if user["totp_pending_secret"]:
        return user["totp_pending_secret"]
    secret = totp.new_secret()
    execute("UPDATE admin_users SET totp_pending_secret = %s WHERE id = %s", (secret, user["id"]))
    return secret


def confirm_setup(username, code):
    """Switches MFA on if the code matches the pending secret. Returns the
    new recovery codes (shown once), or None for a wrong code."""
    user = _user(username)
    counter = totp.match(user["totp_pending_secret"], code)
    if counter is None:
        return None
    execute(
        "UPDATE admin_users SET totp_secret = totp_pending_secret, totp_pending_secret = NULL, "
        "totp_enabled_at = %s, totp_last_counter = %s WHERE id = %s",
        (utc_now(), counter, user["id"]))
    return new_recovery_codes(username)


def turn_off(username) -> None:
    user = _user(username)
    with transaction() as cursor:
        cursor.execute("UPDATE admin_users SET totp_secret = NULL, totp_pending_secret = NULL, "
                       "totp_enabled_at = NULL, totp_last_counter = 0 WHERE id = %s", (user["id"],))
        cursor.execute("DELETE FROM mfa_recovery_codes WHERE user_id = %s", (user["id"],))
        cursor.execute("DELETE FROM trusted_devices WHERE user_id = %s", (user["id"],))


def new_recovery_codes(username) -> list:
    """Replaces all recovery codes; each works once. Stored hashed."""
    user = _user(username)
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(RECOVERY_CODE_COUNT)]
    now = utc_now()
    with transaction() as cursor:
        cursor.execute("DELETE FROM mfa_recovery_codes WHERE user_id = %s", (user["id"],))
        for code in codes:
            cursor.execute("INSERT INTO mfa_recovery_codes (user_id, code_hash, created_at) VALUES (%s, %s, %s)",
                           (user["id"], _hash(_normalize_recovery(code)), now))
    return codes


def recovery_codes_left(username) -> int:
    user = _user(username)
    row = query_one("SELECT COUNT(*) AS n FROM mfa_recovery_codes WHERE user_id = %s AND used_at IS NULL",
                    (user["id"],))
    return row["n"] if row else 0


def _normalize_recovery(code) -> str:
    return "".join(c for c in (code or "").lower() if c in "0123456789abcdef")


# --- checking a code ----------------------------------------------------------------

def verify_code(username, code) -> bool:
    """An authenticator code (each time step usable once) or an unused
    recovery code (burned on use)."""
    user = _user(username)
    if not user or not user["totp_secret"]:
        return False
    counter = totp.match(user["totp_secret"], code)
    if counter is not None:
        # Atomic replay guard: only one request can move the counter forward.
        with transaction() as cursor:
            cursor.execute("UPDATE admin_users SET totp_last_counter = %s WHERE id = %s AND totp_last_counter < %s",
                           (counter, user["id"], counter))
            return cursor.rowcount == 1
    normalized = _normalize_recovery(code)
    if len(normalized) != 12:
        return False
    with transaction() as cursor:
        cursor.execute("UPDATE mfa_recovery_codes SET used_at = %s WHERE user_id = %s AND code_hash = %s "
                       "AND used_at IS NULL", (utc_now(), user["id"], _hash(normalized)))
        return cursor.rowcount == 1


# --- trusted devices ----------------------------------------------------------------

def trust_device(username, label) -> str:
    """Returns the raw token for the gc_device cookie."""
    user = _user(username)
    token = secrets.token_urlsafe(32)
    now = utc_now()
    execute(
        "INSERT INTO trusted_devices (user_id, device_hash, label, created_at, last_used_at, expires_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (user["id"], _hash(token), (label or "Unknown device")[:255], now, now, now + timedelta(days=DEVICE_DAYS)))
    execute("DELETE FROM trusted_devices WHERE expires_at < %s", (now,))
    return token


def device_trusted(username, token) -> bool:
    """True for a known, unexpired device; pushes its expiry a year out
    (at most once a day, so not every page load writes)."""
    if not token:
        return False
    row = query_one(
        "SELECT d.id, d.last_used_at FROM trusted_devices d JOIN admin_users u ON u.id = d.user_id "
        "WHERE u.username = %s AND d.device_hash = %s AND d.expires_at > %s",
        (username, _hash(token), utc_now()))
    if not row:
        return False
    now = utc_now()
    if now - row["last_used_at"] > timedelta(days=1):
        execute("UPDATE trusted_devices SET last_used_at = %s, expires_at = %s WHERE id = %s",
                (now, now + timedelta(days=DEVICE_DAYS), row["id"]))
    return True


def list_devices(username):
    return query(
        "SELECT d.id, d.device_hash, d.label, d.created_at, d.last_used_at FROM trusted_devices d "
        "JOIN admin_users u ON u.id = d.user_id WHERE u.username = %s AND d.expires_at > %s "
        "ORDER BY d.last_used_at DESC", (username, utc_now()))


def remove_device(username, device_id) -> None:
    execute("DELETE d FROM trusted_devices d JOIN admin_users u ON u.id = d.user_id "
            "WHERE u.username = %s AND d.id = %s", (username, device_id))


def device_hash(token) -> str:
    return _hash(token) if token else ""

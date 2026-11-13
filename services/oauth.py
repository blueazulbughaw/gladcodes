"""OAuth 2.1 for the Claude connector (the remote MCP server at
/gc-admin/mcp). Claude registers itself (Dynamic Client Registration),
Glad approves it once on /gc-admin/oauth/authorize with her glad.codes
login, and Claude then holds an access token (1 hour) plus a rotating
refresh token (renewed on use, expires after a year unused).

These tokens only open /gc-admin/mcp, whose tools reach prayers and the
Devotion section, nothing else; they are not admin sessions. Tokens and
codes are stored as SHA-256 hashes, never in plain text. "Disconnect" on
My dashboard revokes every token (revoke_all).
"""
import base64
import calendar
import hashlib
import ipaddress
import json
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from database.db import execute, query_one, transaction, utc_now

SCOPE = "devotion"
ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=365)
CODE_TTL = timedelta(minutes=10)
MAX_NEW_CLIENTS_PER_DAY = 20

# Claude's hosted apps (web, desktop, mobile, Duet) all come back to this
# callback; Claude Code uses a loopback redirect on any port.
HOSTED_CALLBACK_HOSTS = {"claude.ai", "claude.com"}
HOSTED_CALLBACK_PATH = "/api/mcp/auth_callback"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1"}


class OAuthError(Exception):
    def __init__(self, error, description=""):
        super().__init__(description or error)
        self.error = error
        self.description = description


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_loopback(parts) -> bool:
    return parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS


def redirect_uri_allowed(uri) -> bool:
    if not isinstance(uri, str) or len(uri) > 500:
        return False
    try:
        parts = urlsplit(uri)
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError:
        return False
    if parts.fragment or parts.username or parts.password:
        return False
    if parts.scheme == "https" and parts.hostname in HOSTED_CALLBACK_HOSTS:
        return parts.path == HOSTED_CALLBACK_PATH
    return _is_loopback(parts)


def redirect_uri_matches(registered, uri) -> bool:
    """Exact match, except loopback redirects ignore the port (RFC 8252 7.3)."""
    if uri in registered:
        return True
    try:
        parts = urlsplit(uri)
    except ValueError:
        return False
    if not _is_loopback(parts):
        return False
    for reg in registered:
        r = urlsplit(reg)
        if _is_loopback(r) and (r.hostname, r.path, r.query) == (parts.hostname, parts.path, parts.query):
            return True
    return False


# --- clients (Dynamic Client Registration) ---------------------------------

def register_client(metadata) -> dict:
    if not isinstance(metadata, dict):
        raise OAuthError("invalid_client_metadata", "Body must be a JSON object")
    uris = metadata.get("redirect_uris")
    if not isinstance(uris, list) or not 1 <= len(uris) <= 5:
        raise OAuthError("invalid_redirect_uri", "redirect_uris must list 1 to 5 URIs")
    if not all(redirect_uri_allowed(u) for u in uris):
        raise OAuthError("invalid_redirect_uri", "Only Claude's callback URLs are accepted")
    name = metadata.get("client_name")
    name = name.strip()[:100] if isinstance(name, str) and name.strip() else "Claude"

    recent = query_one(
        "SELECT COUNT(*) AS n FROM oauth_clients WHERE created_at > %s",
        (utc_now() - timedelta(days=1),),
    )
    if recent and recent["n"] >= MAX_NEW_CLIENTS_PER_DAY:
        raise OAuthError("invalid_client_metadata", "Too many registrations today")

    client_id = secrets.token_urlsafe(24)
    now = utc_now()
    execute(
        "INSERT INTO oauth_clients (client_id, client_name, redirect_uris, created_at) VALUES (%s, %s, %s, %s)",
        (client_id, name, json.dumps(uris), now),
    )
    return {
        "client_id": client_id,
        "client_id_issued_at": calendar.timegm(now.timetuple()),
        "client_name": name,
        "redirect_uris": uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }


def get_client(client_id):
    if not isinstance(client_id, str) or not client_id or len(client_id) > 64:
        return None
    row = query_one("SELECT client_id, client_name, redirect_uris FROM oauth_clients WHERE client_id = %s", (client_id,))
    if not row:
        return None
    return {"client_id": row["client_id"], "client_name": row["client_name"],
            "redirect_uris": json.loads(row["redirect_uris"] or "[]")}


# --- authorization codes ------------------------------------------------------

def create_code(client_id, redirect_uri, code_challenge) -> str:
    code = secrets.token_urlsafe(32)
    execute(
        "INSERT INTO oauth_codes (code_hash, client_id, redirect_uri, code_challenge, expires_at, used, created_at) "
        "VALUES (%s, %s, %s, %s, %s, 0, %s)",
        (_hash(code), client_id, redirect_uri, code_challenge, utc_now() + CODE_TTL, utc_now()),
    )
    return code


def pkce_matches(verifier, challenge) -> bool:
    if not isinstance(verifier, str) or not 43 <= len(verifier) <= 128:
        return False
    digest = hashlib.sha256(verifier.encode("ascii", "replace")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, challenge or "")


def _issue(cursor, client_id, grant_id) -> dict:
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    now = utc_now()
    for token, kind, ttl in ((access, "access", ACCESS_TTL), (refresh, "refresh", REFRESH_TTL)):
        cursor.execute(
            "INSERT INTO oauth_tokens (token_hash, kind, client_id, grant_id, expires_at, revoked, created_at) "
            "VALUES (%s, %s, %s, %s, %s, 0, %s)",
            (_hash(token), kind, client_id, grant_id, now + ttl, now),
        )
    # Housekeeping: long-expired tokens and old codes are useless.
    cursor.execute("DELETE FROM oauth_tokens WHERE expires_at < %s", (now - timedelta(days=30),))
    cursor.execute("DELETE FROM oauth_codes WHERE expires_at < %s", (now - timedelta(days=1),))
    return {"access_token": access, "token_type": "Bearer", "expires_in": int(ACCESS_TTL.total_seconds()),
            "refresh_token": refresh, "scope": SCOPE}


def exchange_code(client_id, code, redirect_uri, code_verifier) -> dict:
    if not code or not isinstance(code, str):
        raise OAuthError("invalid_request", "code is required")
    with transaction() as cursor:
        cursor.execute("SELECT * FROM oauth_codes WHERE code_hash = %s FOR UPDATE", (_hash(code),))
        row = cursor.fetchone()
        if (not row or row["used"] or row["expires_at"] < utc_now() or row["client_id"] != client_id
                or row["redirect_uri"] != redirect_uri or not pkce_matches(code_verifier, row["code_challenge"])):
            raise OAuthError("invalid_grant", "Invalid or expired authorization code")
        cursor.execute("UPDATE oauth_codes SET used = 1 WHERE id = %s", (row["id"],))
        return _issue(cursor, client_id, secrets.token_hex(16))


def refresh_tokens(client_id, refresh_token) -> dict:
    if not refresh_token or not isinstance(refresh_token, str):
        raise OAuthError("invalid_request", "refresh_token is required")
    with transaction() as cursor:
        cursor.execute(
            "SELECT * FROM oauth_tokens WHERE token_hash = %s AND kind = 'refresh' FOR UPDATE",
            (_hash(refresh_token),),
        )
        row = cursor.fetchone()
        if not row or row["client_id"] != client_id:
            raise OAuthError("invalid_grant", "Invalid refresh token")
        if row["revoked"]:
            # A rotated-out refresh token came back: possible theft, so end
            # the whole connection (Claude will ask to sign in again).
            cursor.execute("UPDATE oauth_tokens SET revoked = 1 WHERE grant_id = %s", (row["grant_id"],))
            raise OAuthError("invalid_grant", "Refresh token already used")
        if row["expires_at"] < utc_now():
            raise OAuthError("invalid_grant", "Refresh token expired")
        cursor.execute("UPDATE oauth_tokens SET revoked = 1 WHERE id = %s", (row["id"],))
        return _issue(cursor, client_id, row["grant_id"])


def check_access_token(token):
    """The token's row if it's a live access token, else None."""
    if not token or len(token) > 200:
        return None
    row = query_one(
        "SELECT id, client_id FROM oauth_tokens WHERE token_hash = %s AND kind = 'access' "
        "AND revoked = 0 AND expires_at > %s",
        (_hash(token), utc_now()),
    )
    if row:
        execute("UPDATE oauth_tokens SET last_used_at = %s WHERE id = %s", (utc_now(), row["id"]))
    return row


# --- My dashboard -------------------------------------------------------------

def connection_status() -> dict:
    row = query_one(
        "SELECT COUNT(*) AS n FROM oauth_tokens WHERE kind = 'refresh' AND revoked = 0 AND expires_at > %s",
        (utc_now(),),
    )
    used = query_one("SELECT MAX(last_used_at) AS last_used FROM oauth_tokens WHERE kind = 'access'")
    return {"connected": bool(row and row["n"]), "last_used": used["last_used"] if used else None}


def revoke_all() -> None:
    execute("UPDATE oauth_tokens SET revoked = 1 WHERE revoked = 0")


# --- network lock ---------------------------------------------------------------

def parse_networks(text):
    networks = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if part:
            networks.append(ipaddress.ip_network(part, strict=False))
    return networks


def ip_allowed(addr, networks) -> bool:
    """True when no lock is configured, or addr is inside one of the networks."""
    if not networks:
        return True
    try:
        ip = ipaddress.ip_address(addr or "")
    except ValueError:
        return False
    return any(ip in net for net in networks if net.version == ip.version)

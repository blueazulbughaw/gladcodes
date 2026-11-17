"""Time-based one-time passwords (RFC 6238: SHA-1, 6 digits, 30 seconds),
the scheme every authenticator app speaks. Standard library only, so no
new dependency for the 3.9 server."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")  # 160 bits, 32 chars, no padding


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** DIGITS).zfill(DIGITS)


def current_counter(now=None) -> int:
    return int((time.time() if now is None else now) // STEP)


def match(secret: str, code: str, now=None, window: int = 1):
    """Returns the matching time-step counter, or None. Accepts one step
    either side for clock drift; the caller rejects counters already used
    so a code can't be replayed."""
    code = "".join(c for c in (code or "") if c.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    counter = current_counter(now)
    found = None
    for candidate in range(counter - window, counter + window + 1):
        if hmac.compare_digest(_code(secret, candidate), code):
            found = candidate
    return found


def provisioning_uri(secret: str, account: str, issuer: str = "GladCodes") -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?" + urlencode({"secret": secret, "issuer": issuer, "digits": DIGITS, "period": STEP})

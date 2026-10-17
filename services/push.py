"""Web Push for the installed check-in app (/gc-admin/today).

VAPID keys: VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY env vars win if set;
otherwise ensure_vapid_keys() (run from passenger_wsgi.py at startup)
generates a pair once and keeps it in checkin_app_state, so push works
after a plain deploy with nothing to configure. Sending is best-effort
like services/mail.py: failures are logged, never raised.
"""
import base64
import json
import logging

from flask import current_app

from database.db import execute, query, query_one

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 5


def generate_vapid_keypair():
    """(public, private) as base64url: raw uncompressed P-256 point / raw scalar."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    def b64url(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64url(public), b64url(key.private_numbers().private_value.to_bytes(32, "big"))


def ensure_vapid_keys() -> None:
    """Load (creating on first run) the VAPID pair into app.config. Needs an
    app context. Race-safe across Passenger workers: only a row with no key
    yet is updated, then every worker reads back whichever pair won."""
    config = current_app.config
    if config.get("VAPID_PUBLIC_KEY") and config.get("VAPID_PRIVATE_KEY"):
        return
    row = query_one("SELECT vapid_public_key, vapid_private_key FROM checkin_app_state WHERE id = 1")
    if not row or not row["vapid_private_key"]:
        public, private = generate_vapid_keypair()
        execute(
            """
            UPDATE checkin_app_state SET vapid_public_key = %s, vapid_private_key = %s
            WHERE id = 1 AND vapid_private_key IS NULL
            """,
            (public, private),
        )
        row = query_one("SELECT vapid_public_key, vapid_private_key FROM checkin_app_state WHERE id = 1")
    if row and row["vapid_private_key"]:
        config["VAPID_PUBLIC_KEY"] = row["vapid_public_key"]
        config["VAPID_PRIVATE_KEY"] = row["vapid_private_key"]


def enabled() -> bool:
    return bool(current_app.config.get("VAPID_PUBLIC_KEY") and current_app.config.get("VAPID_PRIVATE_KEY"))


def save_subscription(endpoint: str, p256dh: str, auth: str, user_agent: str) -> None:
    execute(
        """
        INSERT INTO push_subscriptions (endpoint, p256dh, auth, user_agent)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE p256dh = VALUES(p256dh), auth = VALUES(auth), user_agent = VALUES(user_agent)
        """,
        (endpoint, p256dh, auth, user_agent[:255]),
    )


def delete_subscription(endpoint: str) -> None:
    execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (endpoint,))


def send_to_all(title: str, body: str, url: str, tag: str = "checkin") -> int:
    """Push to every subscribed device. Returns how many accepted it."""
    if not enabled():
        return 0
    from pywebpush import WebPushException, webpush

    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
    claims = {"sub": current_app.config["VAPID_SUBJECT"]}
    sent = 0
    for sub in query("SELECT id, endpoint, p256dh, auth FROM push_subscriptions"):
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload,
                vapid_private_key=current_app.config["VAPID_PRIVATE_KEY"],
                vapid_claims=dict(claims),
                timeout=TIMEOUT_SECONDS,
                ttl=4 * 60 * 60,  # a reminder older than a few hours is noise
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):  # unsubscribed, or the browser dropped it
                execute("DELETE FROM push_subscriptions WHERE id = %s", (sub["id"],))
            else:
                log.warning("Web push failed (%s)", status or type(e).__name__)
        except Exception as e:  # network trouble etc. — never break the caller
            log.warning("Web push failed (%s)", type(e).__name__)
    return sent

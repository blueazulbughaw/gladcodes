"""Web Push for the installed check-in app (/gc-admin/today).

Needs VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY (see config.py); without them
nothing is sent. Best-effort like services/mail.py: any failure is logged
and swallowed — a push never raises into a request or the cron script.
"""
import json
import logging

from flask import current_app

from database.db import execute, query

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 5


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

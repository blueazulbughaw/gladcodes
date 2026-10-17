"""Contact form email delivery via SMTP. Defaults assume a Python app on
cPanel shared hosting, where Exim already handles mail for the domain and
accepts local, unauthenticated submission on localhost:25 — no external
email service (SendGrid/Mailgun/etc.) needed. Never let a delivery failure
crash the page — the caller shows a friendly error and the sender can
always fall back to a direct email.

Recipient: the admin-editable "Contact email" in Settings
(site_settings.contact_email) always wins; the MAIL_TO env var is only a
fallback when Settings is empty. (A stale MAIL_TO=hello@gladcodes.com on
the server, a domain that doesn't exist, used to override everything, so
Exim refused every message with a 550 and the form always failed.)
"""
import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

from database.db import query_one

log = logging.getLogger(__name__)


def contact_recipient():
    row = query_one("SELECT setting_value FROM site_settings WHERE setting_key = 'contact_email'")
    value = (row["setting_value"] or "").strip() if row else ""
    return value or current_app.config.get("MAIL_TO") or None


def send_contact_email(name: str, email: str, subject_choice: str, message: str) -> bool:
    recipient = contact_recipient()
    if not recipient:
        log.error("Contact form: no recipient (set Contact email in admin Settings, or MAIL_TO)")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"GladCodes - {subject_choice}"
    msg["From"] = current_app.config["MAIL_FROM"]
    msg["To"] = recipient
    msg["Reply-To"] = email
    msg.set_content(f"From: {name} <{email}>\nSubject choice: {subject_choice}\n\n{message}")

    try:
        with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=10) as smtp:
            if current_app.config["SMTP_USER"]:
                smtp.starttls()
                smtp.login(current_app.config["SMTP_USER"], current_app.config["SMTP_PASSWORD"])
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        # Logged (it used to fail silently): the SMTP error, never the message body.
        log.error("Contact form email failed: %s: %s", type(e).__name__, e)
        return False

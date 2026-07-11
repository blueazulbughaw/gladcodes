"""Contact form email delivery via SMTP. Defaults assume a Python app on
cPanel shared hosting, where Exim already handles mail for the domain and
accepts local, unauthenticated submission on localhost:25 — no external
email service (SendGrid/Mailgun/etc.) needed. Never let a delivery failure
crash the page — the caller shows a friendly error and the sender can
always fall back to a direct email.
"""
import smtplib
from email.message import EmailMessage

from flask import current_app


def send_contact_email(name: str, email: str, subject_choice: str, message: str) -> bool:
    msg = EmailMessage()
    msg["Subject"] = f"GladCodes - {subject_choice}"
    msg["From"] = current_app.config["MAIL_FROM"]
    msg["To"] = current_app.config["MAIL_TO"]
    msg["Reply-To"] = email
    msg.set_content(f"From: {name} <{email}>\nSubject choice: {subject_choice}\n\n{message}")

    try:
        with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=10) as smtp:
            if current_app.config["SMTP_USER"]:
                smtp.starttls()
                smtp.login(current_app.config["SMTP_USER"], current_app.config["SMTP_PASSWORD"])
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        return False

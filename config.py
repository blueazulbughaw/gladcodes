import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class Config:
    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = FLASK_ENV == "development"

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    JWT_SECRET = os.environ.get("JWT_SECRET", "dev-only-insecure-jwt-secret")
    JWT_EXPIRY_MINUTES = 30

    PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://glad.codes/")

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_NAME = os.environ.get("DB_NAME", "gladcodes_maindb")
    DB_USER = os.environ.get("DB_USER", "gladcodes_admn")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
    GITHUB_CACHE_TTL_SECONDS = 60 * 60  # 1 hour

    # Which calendar day the private daily check-in (/gc-admin/today) counts
    # as "today". The server runs in UTC; this is where Glad actually wakes up.
    LOCAL_TIMEZONE = os.environ.get("LOCAL_TIMEZONE") or "America/New_York"

    # Web Push for check-in reminders (services/push.py, send_reminders.py).
    # Both keys are base64url — generate with `python generate_vapid_keys.py`.
    # Leave empty and nothing is pushed; the app still installs and works.
    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
    VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT") or "https://glad.codes"
    # Local hours (LOCAL_TIMEZONE, 24h clock) when send_reminders.py nudges.
    CHECKIN_MORNING_HOUR = int(os.environ.get("CHECKIN_MORNING_HOUR") or 8)
    CHECKIN_EVENING_HOUR = int(os.environ.get("CHECKIN_EVENING_HOUR") or 21)

    # Contact form delivery. Defaults assume a Python app on cPanel shared
    # hosting, where Exim already handles mail for the account and accepts
    # local, unauthenticated submission on localhost:25 — no external email
    # service needed. Override via env if the host requires authenticated
    # submission instead (e.g. SMTP_PORT=587 + SMTP_USER/SMTP_PASSWORD).
    MAIL_TO = os.environ.get("MAIL_TO", "hello@gladcodes.com")
    MAIL_FROM = os.environ.get("MAIL_FROM", "noreply@glad.codes")
    SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "25"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB upload ceiling

    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
    ALLOWED_RESUME_EXTENSIONS = {"pdf"}

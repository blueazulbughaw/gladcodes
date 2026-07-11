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

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB upload ceiling

    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
    ALLOWED_RESUME_EXTENSIONS = {"pdf"}

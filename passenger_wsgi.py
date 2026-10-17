import logging

from app import app as application
from database.db import apply_schema
from services.push import ensure_vapid_keys

# Self-setup on every app start (deploy restarts trigger it): bring the DB
# schema up to date and make sure push keys exist, so a deploy needs no
# manual SQL import or key generation. Never let it stop the site booting.
with application.app_context():
    try:
        apply_schema()
        ensure_vapid_keys()
    except Exception:
        logging.getLogger(__name__).exception("Startup self-setup failed")

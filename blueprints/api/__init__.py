from flask import Blueprint

# Phase 2 stubs only — no real endpoints yet.
api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

from . import routes  # noqa: E402,F401

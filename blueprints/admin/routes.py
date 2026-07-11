from flask import jsonify

from . import admin_bp

# Auth (JWT cookie + silent-redirect middleware) and all CMS editors are
# built in later steps. This stub exists so the app boots end-to-end.


@admin_bp.route("/")
def index():
    return jsonify(status="ok", message="gc-admin skeleton is running")

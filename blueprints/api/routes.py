from flask import jsonify

from . import api_bp

# Phase 2. No public API surface yet.


@api_bp.route("/status")
def status():
    return jsonify(status="ok", phase="2-stub")

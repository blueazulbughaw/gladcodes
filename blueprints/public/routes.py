from flask import jsonify

from . import public_bp

# Full pages (home, journal, projects, dashboard, resume, speaking, links,
# resources, contact, about) are built in later steps. This stub exists so
# the app boots end-to-end and Passenger has something to serve.


@public_bp.route("/")
def home():
    return jsonify(status="ok", message="GladCodes skeleton is running")

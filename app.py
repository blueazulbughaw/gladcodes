import os
from datetime import timedelta

from flask import Flask, request

from config import Config
from database import db
from services.content import youtube_embed_url


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from blueprints.public import public_bp
    from blueprints.admin import admin_bp
    from blueprints.api import api_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # OAuth discovery for the Claude connector must live under /.well-known/
    # (see blueprints/admin/connector.py); it answers only path-suffixed URLs.
    from blueprints.admin.connector import wellknown_bp
    app.register_blueprint(wellknown_bp)

    @app.template_filter("human_date")
    def human_date(value):
        """Portable replacement for strftime('%-d %B, %Y') — %-d isn't
        supported on Windows, only glibc/macOS, and this app is developed
        on Windows but deployed on Linux."""
        if not value:
            return ""
        return f"{value.strftime('%B')} {value.day}, {value.year}"

    @app.template_filter("human_time")
    def human_time(value):
        """12-hour time display (e.g. '6:00 PM').

        PyMySQL decodes a TIME column as a datetime.timedelta, not a
        datetime.time (TIME is a duration type in MySQL, so it can exceed
        24h) — accept either so this works whether the value came straight
        from a query or was built in Python.
        """
        if value is None:
            return ""
        if isinstance(value, timedelta):
            hour, minute = divmod(int(value.total_seconds() // 60), 60)
        else:
            hour, minute = value.hour, value.minute
        period = "AM" if hour < 12 else "PM"
        hour_12 = hour % 12 or 12
        return f"{hour_12}:{minute:02d} {period}"

    app.jinja_env.filters["youtube_embed"] = youtube_embed_url

    @app.url_defaults
    def static_cache_bust(endpoint, values):
        # Append ?v=<file mtime> to every url_for('static', ...) so a deploy
        # is picked up on the next page load instead of browsers serving a
        # cached stylesheet/script that no longer matches the templates.
        if endpoint != "static" or "filename" not in values:
            return
        path = os.path.join(app.static_folder, values["filename"])
        if os.path.isfile(path):
            values["v"] = int(os.stat(path).st_mtime)

    @app.after_request
    def add_security_headers(response):
        # Nothing on this site is meant to be framed by another site:
        # framing the OAuth approval or admin pages would allow clickjacking.
        # No includeSubDomains on HSTS: cPanel/webmail subdomains aren't ours to promise.
        headers = {
            "Strict-Transport-Security": "max-age=31536000",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        }
        for name, value in headers.items():
            response.headers.setdefault(name, value)
        return response

    @app.after_request
    def add_admin_noindex_header(response):
        # /gc-admin/ is never linked publicly and must never be indexed.
        if request.path.startswith("/gc-admin"):
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])

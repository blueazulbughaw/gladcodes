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

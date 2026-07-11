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

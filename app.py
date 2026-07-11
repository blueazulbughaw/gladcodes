from flask import Flask, request

from config import Config
from database import db


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

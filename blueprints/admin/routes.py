from flask import abort, current_app, g, redirect, render_template, request, url_for

from . import admin_bp
from .auth import (
    COOKIE_NAME,
    clear_attempts,
    is_rate_limited,
    issue_token,
    record_failed_attempt,
    verify_credentials,
    verify_token,
)
from .csrf import CSRF_COOKIE_NAME, csrf_cookie_missing, get_or_create_csrf_token, validate_csrf

# All Phase 1 CMS editors are built in step 7. This is the auth flow only:
# login, logout, the silent-redirect gate, and CSRF protection that every
# future admin POST reuses.


@admin_bp.before_request
def require_auth():
    if request.endpoint == "admin.login":
        return None
    payload = verify_token(request.cookies.get(COOKIE_NAME))
    if payload is None:
        return redirect(url_for("admin.login"))
    g.admin_user = payload["sub"]


@admin_bp.before_request
def csrf_protect():
    if request.method == "POST" and not validate_csrf():
        abort(400)


@admin_bp.context_processor
def inject_csrf():
    return {"csrf_token": get_or_create_csrf_token()}


@admin_bp.after_request
def set_csrf_cookie(response):
    if csrf_cookie_missing():
        response.set_cookie(
            CSRF_COOKIE_NAME,
            get_or_create_csrf_token(),
            httponly=False,
            samesite="Lax",
            secure=not current_app.debug,
        )
    return response


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if is_rate_limited(ip):
            error = "Too many attempts. Try again later."
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if verify_credentials(username, password):
                clear_attempts(ip)
                response = redirect(url_for("admin.index"))
                response.set_cookie(
                    COOKIE_NAME,
                    issue_token(username),
                    httponly=True,
                    secure=not current_app.debug,
                    samesite="Lax",
                    max_age=current_app.config["JWT_EXPIRY_MINUTES"] * 60,
                )
                return response
            record_failed_attempt(ip)
            error = "Invalid username or password."
    return render_template("login.html", error=error)


@admin_bp.route("/logout")
def logout():
    response = redirect(url_for("admin.login"))
    response.delete_cookie(COOKIE_NAME)
    return response


@admin_bp.route("/")
def index():
    return render_template("index.html", user=g.admin_user)

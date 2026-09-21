from flask import abort, current_app, g, redirect, render_template, request, url_for

from database.db import query_one
from services.metrics import get_chart_series

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

# Auth flow (login/logout/silent-redirect/CSRF) plus the dashboard landing
# page. Every other editor lives in its own module (now_card.py, journal.py,
# metrics.py, resume.py, settings.py, simple_crud.py) but shares this
# blueprint, so they all get the auth gate and CSRF protection for free.


@admin_bp.before_request
def require_auth():
    if request.endpoint == "admin.login":
        return None
    payload = verify_token(request.cookies.get(COOKIE_NAME))
    if payload is None:
        return redirect(url_for("admin.login"))
    g.admin_user = payload["sub"]
    g.token_exp = payload["exp"]


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
    post_count = query_one("SELECT COUNT(*) AS c FROM journal_posts")["c"]
    subscriber_count = query_one("SELECT COUNT(*) AS c FROM subscribers WHERE is_active = 1")["c"]
    project_count = query_one("SELECT COUNT(*) AS c FROM projects")["c"]
    now_row = query_one("SELECT updated_at FROM now_card WHERE id = 1")
    coding_hours = get_chart_series("coding_hours_weekly")

    return render_template(
        "index.html",
        token_exp=g.token_exp,
        post_count=post_count,
        subscriber_count=subscriber_count,
        project_count=project_count,
        now_updated_at=now_row["updated_at"] if now_row else None,
        coding_hours=coding_hours,
    )

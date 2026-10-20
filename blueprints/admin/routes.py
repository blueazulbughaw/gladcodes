from flask import abort, current_app, g, redirect, render_template, request, url_for

from database.db import query_one
from services.metrics import get_chart_series

from . import admin_bp
from .checkin import checkin_streak, has_checked_in, local_today
from .auth import (
    COOKIE_NAME,
    clear_attempts,
    is_rate_limited,
    issue_token,
    token_lifetime,
    record_failed_attempt,
    verify_credentials,
    verify_token,
)
from .csrf import CSRF_COOKIE_NAME, csrf_cookie_missing, get_or_create_csrf_token, validate_csrf

# Auth flow (login/logout/silent-redirect/CSRF) plus the dashboard landing
# page. Every other editor lives in its own module (now_card.py, journal.py,
# metrics.py, resume.py, settings.py, simple_crud.py) but shares this
# blueprint, so they all get the auth gate and CSRF protection for free.


# Phone automations (personal.py): no browser session, so no JWT cookie or
# CSRF cookie — they authenticate with a bearer token instead.
TOKEN_ENDPOINTS = {"admin.track_sleep", "admin.track_app"}

# Reachable without a session: the login form, the installable app's
# manifest and service worker, and the cron-pinged reminder tick (see
# app_shell.py for why each is safe), plus the token-checked endpoints.
PUBLIC_ENDPOINTS = {"admin.login", "admin.manifest", "admin.service_worker", "admin.reminders_tick"} | TOKEN_ENDPOINTS


@admin_bp.before_request
def require_auth():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    payload = verify_token(request.cookies.get(COOKIE_NAME))
    if payload is None:
        return redirect(url_for("admin.login"))
    g.admin_user = payload["sub"]
    g.token_exp = payload["exp"]


@admin_bp.before_request
def csrf_protect():
    if request.method == "POST" and request.endpoint not in TOKEN_ENDPOINTS and not validate_csrf():
        abort(400)


@admin_bp.context_processor
def inject_csrf():
    return {"csrf_token": get_or_create_csrf_token()}


# Pages that are a "home" (no Back button) and personal resources whose
# lists sit under Today rather than the site dashboard.
NO_BACK_ENDPOINTS = {"admin.today", "admin.index", "admin.login"}
PERSONAL_RESOURCES = {"medications", "app_ideas"}
MONEY_RESOURCES = {"recurring_bills", "credit_cards"}


def back_url():
    """Where the Back button goes: the page's parent, not browser history
    (history.back() after saving a form lands on the stale form, and the
    installed app has no browser back button). Edit/create → its list;
    personal pages → Today; site editors → their index or the site dashboard."""
    endpoint = request.endpoint or ""
    if endpoint in NO_BACK_ENDPOINTS:
        return None
    resource = (request.view_args or {}).get("resource")
    if resource and endpoint != "admin.simple_list":
        return url_for("admin.simple_list", resource=resource)
    if resource in MONEY_RESOURCES:
        return url_for("admin.money_index")
    if resource in PERSONAL_RESOURCES or endpoint in ("admin.personal_dashboard", "admin.money_index"):
        return url_for("admin.today")
    name = endpoint.split(".", 1)[-1]
    index = f"admin.{name.rsplit('_', 1)[0]}_index"  # journal_edit -> journal_index
    if index != endpoint and index in current_app.view_functions:
        return url_for(index)
    return url_for("admin.index")


@admin_bp.context_processor
def inject_back_url():
    return {"back_url": back_url()}


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
                # Morning ritual: land on the daily check-in until today's is done.
                landing = "admin.personal_dashboard" if has_checked_in(local_today()) else "admin.today"
                response = redirect(url_for(landing))
                remember = request.form.get("remember") == "1"
                response.set_cookie(
                    COOKIE_NAME,
                    issue_token(username, remember),
                    httponly=True,
                    secure=not current_app.debug,
                    samesite="Lax",
                    max_age=int(token_lifetime(remember).total_seconds()),
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
    today_date = local_today()

    return render_template(
        "index.html",
        token_exp=g.token_exp,
        checked_in_today=has_checked_in(today_date),
        checkin_streak=checkin_streak(today_date),
        post_count=post_count,
        subscriber_count=subscriber_count,
        project_count=project_count,
        now_updated_at=now_row["updated_at"] if now_row else None,
        coding_hours=coding_hours,
    )

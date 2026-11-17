"""Authenticator sign-in for the admin (see services/mfa.py for the rules).

session_state() is what the auth gate (routes.require_auth) and the OAuth
approval page ask on every request; /login/verify is the code step after a
correct password on an untrusted device; /security sets it up and lists the
trusted devices.
"""
from datetime import datetime, timezone

from flask import current_app, g, redirect, render_template, request, url_for

from services import mfa as mfa_service
from services import totp

from . import admin_bp
from .auth import (
    COOKIE_NAME,
    PENDING_COOKIE,
    clear_attempts,
    is_rate_limited,
    issue_token,
    record_failed_attempt,
    token_lifetime,
    verify_pending_token,
    verify_token,
)

DEVICE_COOKIE = mfa_service.DEVICE_COOKIE


def session_state(payload, device_token) -> str:
    """"ok", "trust" (signed in before MFA was switched on: register this
    device now, so devices already signed in are never asked) or "deny"
    (a removed device, or a newer session that skipped the code step)."""
    enabled = mfa_service.enabled_at(payload["sub"])
    if enabled is None:
        return "ok"
    if device_token:
        return "ok" if mfa_service.device_trusted(payload["sub"], device_token) else "deny"
    issued = datetime.fromtimestamp(payload["iat"], timezone.utc).replace(tzinfo=None)
    return "trust" if issued < enabled else "deny"


def current_admin():
    """The session payload if this request is fully signed in, else None."""
    payload = verify_token(request.cookies.get(COOKIE_NAME))
    if payload is None:
        return None
    state = session_state(payload, request.cookies.get(DEVICE_COOKIE))
    if state == "deny":
        return None
    if state == "trust":
        g.trust_device_for = payload["sub"]
    return payload


def needs_code(username) -> bool:
    return (mfa_service.enabled_at(username) is not None
            and not mfa_service.device_trusted(username, request.cookies.get(DEVICE_COOKIE)))


def device_label(user_agent: str) -> str:
    ua = user_agent or ""
    browser = next((name for key, name in (("SamsungBrowser", "Samsung Internet"), ("Edg/", "Edge"),
                                           ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
                    if key in ua), "Browser")
    system = next((name for key, name in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
                                          ("Windows", "Windows"), ("Mac OS", "Mac"), ("Linux", "Linux"))
                   if key in ua), "")
    return f"{browser} on {system}" if system else browser


def _cookie_args(max_age):
    return {"httponly": True, "secure": not current_app.debug, "samesite": "Lax", "max_age": max_age}


def set_device_cookie(response, token):
    response.set_cookie(DEVICE_COOKIE, token, **_cookie_args(mfa_service.DEVICE_DAYS * 24 * 3600))


def finish_sign_in(username, remember, trust_device=False):
    """Session cookie + landing page, shared by the password and code steps."""
    response = redirect(url_for("admin.personal_dashboard"))
    response.set_cookie(COOKIE_NAME, issue_token(username, remember),
                        **_cookie_args(int(token_lifetime(remember).total_seconds())))
    if trust_device:
        set_device_cookie(response, mfa_service.trust_device(username, device_label(request.user_agent.string)))
    response.delete_cookie(PENDING_COOKIE)
    return response


@admin_bp.after_request
def register_existing_device(response):
    username = g.pop("trust_device_for", None)
    if username:
        set_device_cookie(response, mfa_service.trust_device(username, device_label(request.user_agent.string)))
    return response


@admin_bp.route("/login/verify", methods=["GET", "POST"])
def login_verify():
    pending = verify_pending_token(request.cookies.get(PENDING_COOKIE))
    if pending is None:
        return redirect(url_for("admin.login"))
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        username = pending["sub"]
        if is_rate_limited(ip, username):
            error = "Too many attempts. Try again later."
        elif mfa_service.verify_code(username, request.form.get("code", "")):
            clear_attempts(ip)
            return finish_sign_in(username, pending.get("remember", False), trust_device=True)
        else:
            record_failed_attempt(ip, username)
            error = "That code didn't work. Try the newest one."
    return render_template("login_verify.html", error=error)


@admin_bp.route("/security", methods=["GET", "POST"])
def security():
    username = g.admin_user
    this_device = mfa_service.device_hash(request.cookies.get(DEVICE_COOKIE))
    message = error = None
    recovery_codes = None
    new_device_token = None

    if request.method == "POST":
        action = request.form.get("action")
        code = request.form.get("code", "")
        if action == "enable":
            recovery_codes = mfa_service.confirm_setup(username, code)
            if recovery_codes is None:
                error = "That code didn't match. Check the time on your phone and try the newest code."
            else:
                # This device just proved the code, so it's trusted from now on.
                new_device_token = mfa_service.trust_device(username, device_label(request.user_agent.string))
                this_device = mfa_service.device_hash(new_device_token)
                message = "Authenticator is on."
        elif action == "remove_device":
            try:
                mfa_service.remove_device(username, int(request.form.get("device_id", "")))
            except ValueError:
                pass
            return redirect(url_for("admin.security"))
        elif action in ("new_codes", "turn_off"):
            if not mfa_service.verify_code(username, code):
                error = "That code didn't work."
            elif action == "new_codes":
                recovery_codes = mfa_service.new_recovery_codes(username)
                message = "New backup codes made. The old ones no longer work."
            else:
                mfa_service.turn_off(username)
                message = "Authenticator is off."

    enabled = mfa_service.enabled_at(username) is not None
    context = {"enabled": enabled, "message": message, "error": error, "recovery_codes": recovery_codes}
    if enabled:
        context.update(devices=mfa_service.list_devices(username), this_device=this_device,
                       codes_left=mfa_service.recovery_codes_left(username))
    else:
        secret = mfa_service.pending_secret(username)
        context.update(secret=secret, otpauth=totp.provisioning_uri(secret, username))
    response = current_app.make_response(render_template("security.html", **context))
    response.headers["Cache-Control"] = "no-store"  # shows a secret / backup codes
    if new_device_token:
        set_device_cookie(response, new_device_token)
    return response

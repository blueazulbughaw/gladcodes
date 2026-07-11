"""Double-submit-cookie CSRF protection for admin POSTs.

No server-side session store exists (auth is a stateless JWT cookie), so
CSRF uses the double-submit pattern instead of Flask-WTF's session-token
approach: a random token is set as a cookie and must also be echoed back
as a hidden form field on every POST. A forged cross-site POST can't read
the cookie, so it can't supply a matching field value.
"""
import secrets

from flask import g, request

CSRF_COOKIE_NAME = "gc_csrf"
CSRF_FORM_FIELD = "csrf_token"


def get_or_create_csrf_token() -> str:
    if "csrf_token" not in g:
        g.csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or secrets.token_urlsafe(32)
    return g.csrf_token


def csrf_cookie_missing() -> bool:
    return CSRF_COOKIE_NAME not in request.cookies


def validate_csrf() -> bool:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    form_token = request.form.get(CSRF_FORM_FIELD)
    return bool(cookie_token) and bool(form_token) and secrets.compare_digest(cookie_token, form_token)

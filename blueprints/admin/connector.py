"""The Claude connector: a remote MCP server at /gc-admin/mcp that Claude
Duet uses to save Glad's prayers and devotions, protected by OAuth 2.1
(services/oauth.py) that Glad approves once with her glad.codes login.

Discovery follows Claude's connector docs: an unauthenticated call to
/gc-admin/mcp gets a 401 pointing at the protected-resource metadata, which
names the authorization server (issuer /gc-admin/oauth); Claude registers
itself, sends Glad to /gc-admin/oauth/authorize, and swaps the code for
tokens at /gc-admin/oauth/token.

The /.well-known/ documents live on wellknown_bp (no /gc-admin prefix,
since OAuth discovery requires those paths) but only answer at the exact
path-suffixed URLs, so they reveal nothing to anyone who doesn't already
know the admin path. Nothing public links to any of this.

/gc-admin/mcp, /token and /register only answer Anthropic's servers
(MCP_ALLOWED_NETWORKS); anyone else gets a plain 404.
"""
import logging
import traceback
from urllib.parse import urlencode, urlsplit

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for

from services import mcp_server, oauth

from . import admin_bp
from .auth import COOKIE_NAME, clear_attempts, is_rate_limited, record_failed_attempt, verify_credentials, verify_token
from .checkin import local_today

log = logging.getLogger(__name__)

wellknown_bp = Blueprint("wellknown", __name__)


# --- URLs -------------------------------------------------------------------

def _base():
    return current_app.config["PUBLIC_SITE_URL"].rstrip("/")


def resource_url():
    return _base() + "/gc-admin/mcp"


def issuer_url():
    return _base() + "/gc-admin/oauth"


def resource_metadata_url():
    return _base() + "/.well-known/oauth-protected-resource/gc-admin/mcp"


def _private_json(data, status=200):
    response = jsonify(data)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _network_ok() -> bool:
    networks = oauth.parse_networks(current_app.config.get("MCP_ALLOWED_NETWORKS", ""))
    if oauth.ip_allowed(request.remote_addr, networks):
        return True
    log.warning("Connector request refused from %s (%s)", request.remote_addr, request.path)
    return False


# --- discovery metadata -------------------------------------------------------

def protected_resource_metadata():
    return {
        "resource": resource_url(),
        "authorization_servers": [issuer_url()],
        "scopes_supported": [oauth.SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "glad.codes devotions",
    }


def authorization_server_metadata():
    issuer = issuer_url()
    return {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/authorize",
        "token_endpoint": issuer + "/token",
        "registration_endpoint": issuer + "/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [oauth.SCOPE],
    }


@wellknown_bp.route("/.well-known/oauth-protected-resource/gc-admin/mcp")
def protected_resource():
    return _private_json(protected_resource_metadata())


@wellknown_bp.route("/.well-known/oauth-authorization-server/gc-admin/oauth")
@wellknown_bp.route("/.well-known/openid-configuration/gc-admin/oauth")
def authorization_server():
    return _private_json(authorization_server_metadata())


@admin_bp.route("/oauth/.well-known/openid-configuration", endpoint="oauth_metadata")
@admin_bp.route("/oauth/.well-known/oauth-authorization-server", endpoint="oauth_metadata")
def oauth_metadata():
    return _private_json(authorization_server_metadata())


# --- registration + tokens (called by Claude's servers) -----------------------

@admin_bp.route("/oauth/register", methods=["POST"])
def oauth_register():
    if not _network_ok():
        abort(404)
    try:
        client = oauth.register_client(request.get_json(silent=True))
    except oauth.OAuthError as err:
        return _private_json({"error": err.error, "error_description": err.description}, 400)
    return _private_json(client, 201)


@admin_bp.route("/oauth/token", methods=["POST"])
def oauth_token():
    if not _network_ok():
        abort(404)
    form = request.form if request.form else (request.get_json(silent=True) or {})
    client_id = form.get("client_id") or (request.authorization.username if request.authorization else None)
    if not oauth.get_client(client_id):
        return _private_json({"error": "invalid_client"}, 401)
    grant = form.get("grant_type")
    try:
        if grant == "authorization_code":
            tokens = oauth.exchange_code(client_id, form.get("code"), form.get("redirect_uri"), form.get("code_verifier"))
        elif grant == "refresh_token":
            tokens = oauth.refresh_tokens(client_id, form.get("refresh_token"))
        else:
            return _private_json({"error": "unsupported_grant_type"}, 400)
    except oauth.OAuthError as err:
        return _private_json({"error": err.error, "error_description": err.description}, 400)
    return _private_json(tokens)


# --- the approval page (Glad, once, in her browser) ----------------------------

AUTHORIZE_PARAMS = ("response_type", "client_id", "redirect_uri", "code_challenge",
                    "code_challenge_method", "state", "scope", "resource")


def _back_to_client(redirect_uri, **params):
    sep = "&" if "?" in redirect_uri else "?"
    return redirect(redirect_uri + sep + urlencode({k: v for k, v in params.items() if v}))


@admin_bp.route("/oauth/authorize", methods=["GET", "POST"])
def oauth_authorize():
    source = request.form if request.method == "POST" else request.args
    params = {name: source.get(name, "") for name in AUTHORIZE_PARAMS}
    client = oauth.get_client(params["client_id"])
    if not client or not oauth.redirect_uri_matches(client["redirect_uris"], params["redirect_uri"]):
        # Can't trust where to send an error, so don't send anyone anywhere.
        return "Invalid request.", 400, {"Content-Type": "text/plain; charset=utf-8"}
    redirect_uri, state = params["redirect_uri"], params["state"]
    if (params["response_type"] != "code" or params["code_challenge_method"] != "S256"
            or not 43 <= len(params["code_challenge"]) <= 128):
        return _back_to_client(redirect_uri, error="invalid_request", state=state)

    signed_in = verify_token(request.cookies.get(COOKIE_NAME)) is not None
    error = None
    if request.method == "POST":
        if request.form.get("decision") != "allow":
            return _back_to_client(redirect_uri, error="access_denied", state=state)
        if not signed_in:
            ip = request.remote_addr or "unknown"
            if is_rate_limited(ip):
                error = "Too many attempts. Try again later."
            elif verify_credentials(request.form.get("username", "").strip(), request.form.get("password", "")):
                clear_attempts(ip)
                signed_in = True
            else:
                record_failed_attempt(ip)
                error = "Invalid username or password."
        if signed_in and not error:
            code = oauth.create_code(client["client_id"], redirect_uri, params["code_challenge"])
            return _back_to_client(redirect_uri, code=code, state=state)

    return render_template(
        "oauth_authorize.html",
        params=params,
        signed_in=signed_in,
        error=error,
        return_host=urlsplit(redirect_uri).hostname,
    )


# --- the MCP endpoint ---------------------------------------------------------

def _unauthorized(had_token: bool):
    challenge = f'Bearer resource_metadata="{resource_metadata_url()}", scope="{oauth.SCOPE}"'
    if had_token:
        challenge += ', error="invalid_token"'
    response = _private_json({"error": "unauthorized"}, 401)
    response.headers["WWW-Authenticate"] = challenge
    return response


@admin_bp.route("/mcp", methods=["GET", "POST", "DELETE"])
def mcp():
    if not _network_ok():
        abort(404)
    origin = request.headers.get("Origin")
    if origin and urlsplit(origin).hostname not in oauth.HOSTED_CALLBACK_HOSTS:
        abort(403)  # DNS-rebinding guard from the MCP transport spec
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header[:7].lower() == "bearer " else ""
    if not oauth.check_access_token(token):
        return _unauthorized(bool(token))
    if request.method != "POST":
        # No server-initiated stream and no sessions: every reply is plain JSON.
        return "", 405, {"Allow": "POST"}
    body = request.get_json(silent=True)
    if body is None:
        return _private_json({"jsonrpc": "2.0", "id": None,
                              "error": {"code": -32700, "message": "Parse error"}}, 400)
    try:
        reply = mcp_server.handle(body, local_today)
    except Exception as exc:  # log where it failed, never the message (it could quote prayer text)
        log.error("Connector call failed (%s): %s", type(exc).__name__,
                  "".join(traceback.format_tb(exc.__traceback__)))
        return _private_json({"jsonrpc": "2.0", "id": body.get("id") if isinstance(body, dict) else None,
                              "error": {"code": -32603, "message": "Something went wrong on glad.codes"}}, 500)
    if reply is None:
        return "", 202
    return _private_json(reply)


# --- Connectors -> Claude connector (Glad's page) -------------------------------

@admin_bp.route("/connectors/claude")
def connector_claude():
    return render_template("connector_claude.html", connector=oauth.connection_status(), connector_url=resource_url())


@admin_bp.route("/connectors/claude/disconnect", methods=["POST"])
def connector_disconnect():
    oauth.revoke_all()
    return redirect(url_for("admin.connector_claude"))

"""The Claude connector: OAuth discovery/registration/approval/tokens
(services/oauth.py, blueprints/admin/connector.py) and the MCP endpoint
(services/mcp_server.py)."""
import json
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from app import create_app
from blueprints.admin.auth import COOKIE_NAME, issue_token
from blueprints.admin.csrf import CSRF_COOKIE_NAME
from database.db import utc_now
from services import devotion, mcp_server, oauth

ANTHROPIC_IP = {"REMOTE_ADDR": "160.79.104.10"}
CALLBACK = "https://claude.ai/api/mcp/auth_callback"
CLIENT = {"client_id": "client-1", "client_name": "Claude", "redirect_uris": [CALLBACK]}
# RFC 7636 appendix B example
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
TODAY = date(2026, 11, 13)


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def sql(self, start):
        return [c for c in self.calls if c[0].startswith(start)]


def fake_tx(cursor):
    from contextlib import contextmanager

    @contextmanager
    def _tx():
        yield cursor
    return _tx


class Base(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, PUBLIC_SITE_URL="https://glad.codes/")
        self.client = self.app.test_client()


class OAuthHelperTests(unittest.TestCase):
    def test_pkce_rfc7636_vector(self):
        self.assertTrue(oauth.pkce_matches(VERIFIER, CHALLENGE))
        self.assertFalse(oauth.pkce_matches(VERIFIER[:-1] + "x", CHALLENGE))
        self.assertFalse(oauth.pkce_matches(None, CHALLENGE))

    def test_only_claude_callbacks_can_register(self):
        for ok in (CALLBACK, "https://claude.com/api/mcp/auth_callback", "http://localhost:3118/callback",
                   "http://127.0.0.1:9999/callback"):
            self.assertTrue(oauth.redirect_uri_allowed(ok), ok)
        for bad in ("https://evil.example/api/mcp/auth_callback", "https://claude.ai/other",
                    "http://claude.ai/api/mcp/auth_callback", "https://claude.ai.evil.com/api/mcp/auth_callback",
                    "https://user@claude.ai/api/mcp/auth_callback", "javascript:alert(1)", None, "x" * 600):
            self.assertFalse(oauth.redirect_uri_allowed(bad), bad)

    def test_loopback_redirect_ignores_port_only(self):
        reg = ["http://localhost:3118/callback"]
        self.assertTrue(oauth.redirect_uri_matches(reg, "http://localhost:5000/callback"))
        self.assertFalse(oauth.redirect_uri_matches(reg, "http://localhost:5000/other"))
        self.assertFalse(oauth.redirect_uri_matches([CALLBACK], "https://claude.com/api/mcp/auth_callback"))

    def test_network_lock(self):
        nets = oauth.parse_networks("160.79.104.0/21, 153.61.208.0/20")
        self.assertTrue(oauth.ip_allowed("160.79.111.255", nets))
        self.assertTrue(oauth.ip_allowed("153.61.223.1", nets))
        self.assertFalse(oauth.ip_allowed("160.79.112.0", nets))
        self.assertFalse(oauth.ip_allowed("2607:6bc0::1", nets))
        self.assertFalse(oauth.ip_allowed("garbage", nets))
        self.assertTrue(oauth.ip_allowed("1.2.3.4", []))

    def test_code_exchange_checks_everything_and_is_single_use(self):
        good = {"id": 5, "used": 0, "expires_at": utc_now() + timedelta(minutes=5), "client_id": "client-1",
                "redirect_uri": CALLBACK, "code_challenge": CHALLENGE}
        cursor = FakeCursor([dict(good)])
        with patch("services.oauth.transaction", fake_tx(cursor)):
            tokens = oauth.exchange_code("client-1", "the-code", CALLBACK, VERIFIER)
        self.assertEqual(tokens["token_type"], "Bearer")
        self.assertEqual(tokens["expires_in"], 3600)
        self.assertEqual(cursor.sql("UPDATE oauth_codes SET used = 1")[0][1], (5,))
        stored = [p[0] for _, p in cursor.sql("INSERT INTO oauth_tokens")]
        self.assertNotIn(tokens["access_token"], stored)  # only hashes are stored
        self.assertEqual(len(stored[0]), 64)

        for bad in (dict(good, used=1), dict(good, client_id="other"), dict(good, redirect_uri="http://localhost/x"),
                    dict(good, expires_at=utc_now() - timedelta(seconds=1))):
            with patch("services.oauth.transaction", fake_tx(FakeCursor([bad]))):
                with self.assertRaises(oauth.OAuthError):
                    oauth.exchange_code("client-1", "the-code", CALLBACK, VERIFIER)
        with patch("services.oauth.transaction", fake_tx(FakeCursor([dict(good)]))):
            with self.assertRaises(oauth.OAuthError):
                oauth.exchange_code("client-1", "the-code", CALLBACK, "wrong-verifier-" + "x" * 40)

    def test_refresh_rotates_and_reuse_ends_the_connection(self):
        row = {"id": 9, "client_id": "client-1", "grant_id": "g" * 32, "revoked": 0,
               "expires_at": utc_now() + timedelta(days=10)}
        cursor = FakeCursor([dict(row)])
        with patch("services.oauth.transaction", fake_tx(cursor)):
            tokens = oauth.refresh_tokens("client-1", "old-refresh")
        self.assertIn("refresh_token", tokens)
        self.assertEqual(cursor.sql("UPDATE oauth_tokens SET revoked = 1 WHERE id")[0][1], (9,))
        self.assertEqual(cursor.sql("INSERT INTO oauth_tokens")[0][1][3], "g" * 32)  # same grant

        cursor = FakeCursor([dict(row, revoked=1)])
        with patch("services.oauth.transaction", fake_tx(cursor)):
            with self.assertRaises(oauth.OAuthError):
                oauth.refresh_tokens("client-1", "old-refresh")
        self.assertEqual(cursor.sql("UPDATE oauth_tokens SET revoked = 1 WHERE grant_id")[0][1], ("g" * 32,))


class DiscoveryTests(Base):
    def test_metadata_documents(self):
        prm = self.client.get("/.well-known/oauth-protected-resource/gc-admin/mcp").get_json()
        self.assertEqual(prm["resource"], "https://glad.codes/gc-admin/mcp")
        self.assertEqual(prm["authorization_servers"], ["https://glad.codes/gc-admin/oauth"])
        for path in ("/.well-known/oauth-authorization-server/gc-admin/oauth",
                     "/.well-known/openid-configuration/gc-admin/oauth",
                     "/gc-admin/oauth/.well-known/openid-configuration",
                     "/gc-admin/oauth/.well-known/oauth-authorization-server"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)
            meta = resp.get_json()
            self.assertEqual(meta["issuer"], "https://glad.codes/gc-admin/oauth")
            self.assertEqual(meta["code_challenge_methods_supported"], ["S256"])
            self.assertEqual(meta["registration_endpoint"], "https://glad.codes/gc-admin/oauth/register")
            self.assertEqual(resp.headers["X-Robots-Tag"], "noindex, nofollow")

    def test_bare_well_known_paths_reveal_nothing(self):
        for path in ("/.well-known/oauth-authorization-server", "/.well-known/oauth-protected-resource",
                     "/.well-known/openid-configuration"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


class RegisterTests(Base):
    @patch("services.oauth.execute")
    @patch("services.oauth.query_one", return_value={"n": 0})
    def test_registers_claude(self, _q, mock_execute):
        resp = self.client.post("/gc-admin/oauth/register", json={"redirect_uris": [CALLBACK], "client_name": "Claude"},
                                environ_base=ANTHROPIC_IP)
        self.assertEqual(resp.status_code, 201)
        body = resp.get_json()
        self.assertEqual(body["token_endpoint_auth_method"], "none")
        self.assertEqual(body["redirect_uris"], [CALLBACK])
        self.assertTrue(mock_execute.called)

    @patch("services.oauth.execute")
    @patch("services.oauth.query_one", return_value={"n": 0})
    def test_rejects_other_callbacks_and_strangers(self, _q, mock_execute):
        resp = self.client.post("/gc-admin/oauth/register", json={"redirect_uris": ["https://evil.example/cb"]},
                                environ_base=ANTHROPIC_IP)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "invalid_redirect_uri")
        resp = self.client.post("/gc-admin/oauth/register", json={"redirect_uris": [CALLBACK]})  # 127.0.0.1
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(mock_execute.called)

    @patch("services.oauth.execute")
    @patch("services.oauth.query_one", return_value={"n": 20})
    def test_registration_is_rate_limited(self, *_):
        resp = self.client.post("/gc-admin/oauth/register", json={"redirect_uris": [CALLBACK]}, environ_base=ANTHROPIC_IP)
        self.assertEqual(resp.status_code, 400)


@patch("blueprints.admin.connector.oauth.get_client", side_effect=lambda cid: CLIENT if cid == "client-1" else None)
class AuthorizeTests(Base):
    QUERY = {"response_type": "code", "client_id": "client-1", "redirect_uri": CALLBACK,
             "code_challenge": CHALLENGE, "code_challenge_method": "S256", "state": "xyz", "scope": "devotion"}

    def sign_in(self):
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))

    def test_unknown_client_or_redirect_goes_nowhere(self, _):
        resp = self.client.get("/gc-admin/oauth/authorize", query_string=dict(self.QUERY, client_id="nope"))
        self.assertEqual(resp.status_code, 400)
        resp = self.client.get("/gc-admin/oauth/authorize", query_string=dict(self.QUERY, redirect_uri="https://evil.example/"))
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("Location", resp.headers)

    def test_missing_pkce_is_sent_back_as_an_error(self, _):
        resp = self.client.get("/gc-admin/oauth/authorize", query_string=dict(self.QUERY, code_challenge_method="plain"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("error=invalid_request", resp.headers["Location"])

    def test_signed_out_page_asks_for_password(self, _):
        body = self.client.get("/gc-admin/oauth/authorize", query_string=self.QUERY).get_data(as_text=True)
        self.assertIn("Connect Claude", body)
        self.assertIn('name="password"', body)
        self.assertIn("claude.ai", body)
        self.assertIn('content="noindex, nofollow"', body.replace("noindex,nofollow", "noindex, nofollow"))

    @patch("blueprints.admin.connector.is_rate_limited", return_value=False)
    @patch("blueprints.admin.connector.record_failed_attempt")
    @patch("blueprints.admin.connector.clear_attempts")
    @patch("blueprints.admin.connector.verify_credentials", return_value=False)
    @patch("blueprints.admin.connector.oauth.create_code")
    def test_wrong_password_gives_no_code(self, mock_code, *args):
        self.client.set_cookie(CSRF_COOKIE_NAME, "t")
        resp = self.client.post("/gc-admin/oauth/authorize", data=dict(self.QUERY, csrf_token="t", decision="allow",
                                                                        username="glad", password="nope"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Invalid username or password.", resp.get_data(as_text=True))
        self.assertFalse(mock_code.called)
        mock_record = args[2]  # verify_credentials, clear_attempts, record_failed_attempt, ...
        mock_record.assert_called_once_with("127.0.0.1", "glad")

    @patch("blueprints.admin.connector.is_rate_limited", return_value=False)
    @patch("blueprints.admin.connector.record_failed_attempt")
    @patch("blueprints.admin.connector.clear_attempts")
    @patch("blueprints.admin.connector.verify_credentials", return_value=True)
    @patch("blueprints.admin.connector.oauth.create_code", return_value="CODE123")
    def test_password_then_allow_sends_code_back(self, mock_code, *_):
        self.client.set_cookie(CSRF_COOKIE_NAME, "t")
        resp = self.client.post("/gc-admin/oauth/authorize", data=dict(self.QUERY, csrf_token="t", decision="allow",
                                                                        username="glad", password="right"))
        self.assertEqual(resp.status_code, 302)
        loc = urlsplit(resp.headers["Location"])
        self.assertEqual(f"{loc.scheme}://{loc.netloc}{loc.path}", CALLBACK)
        self.assertEqual(parse_qs(loc.query), {"code": ["CODE123"], "state": ["xyz"]})
        mock_code.assert_called_once_with("client-1", CALLBACK, CHALLENGE)

    @patch("blueprints.admin.connector.oauth.create_code", return_value="CODE123")
    def test_signed_in_just_allows(self, mock_code, _):
        self.sign_in()
        body = self.client.get("/gc-admin/oauth/authorize", query_string=self.QUERY).get_data(as_text=True)
        self.assertNotIn('name="password"', body)
        self.client.set_cookie(CSRF_COOKIE_NAME, "t")
        resp = self.client.post("/gc-admin/oauth/authorize", data=dict(self.QUERY, csrf_token="t", decision="allow"))
        self.assertIn("code=CODE123", resp.headers["Location"])

    def test_cancel_and_csrf(self, _):
        self.sign_in()
        self.client.set_cookie(CSRF_COOKIE_NAME, "t")
        resp = self.client.post("/gc-admin/oauth/authorize", data=dict(self.QUERY, csrf_token="t", decision="deny"))
        self.assertIn("error=access_denied", resp.headers["Location"])
        resp = self.client.post("/gc-admin/oauth/authorize", data=dict(self.QUERY, csrf_token="bad", decision="allow"))
        self.assertEqual(resp.status_code, 400)


class TokenEndpointTests(Base):
    @patch("blueprints.admin.connector.oauth.get_client", return_value=CLIENT)
    @patch("blueprints.admin.connector.oauth.exchange_code", return_value={"access_token": "a", "token_type": "Bearer"})
    def test_form_encoded_code_exchange(self, mock_exchange, _):
        resp = self.client.post("/gc-admin/oauth/token", environ_base=ANTHROPIC_IP, data={
            "grant_type": "authorization_code", "client_id": "client-1", "code": "c",
            "redirect_uri": CALLBACK, "code_verifier": VERIFIER})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["Cache-Control"], "no-store")
        mock_exchange.assert_called_once_with("client-1", "c", CALLBACK, VERIFIER)

    @patch("blueprints.admin.connector.oauth.get_client", return_value=CLIENT)
    @patch("blueprints.admin.connector.oauth.refresh_tokens", side_effect=oauth.OAuthError("invalid_grant", "x"))
    def test_bad_refresh_is_invalid_grant(self, *_):
        resp = self.client.post("/gc-admin/oauth/token", environ_base=ANTHROPIC_IP,
                                data={"grant_type": "refresh_token", "client_id": "client-1", "refresh_token": "r"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "invalid_grant")

    @patch("blueprints.admin.connector.oauth.get_client", return_value=None)
    def test_unknown_client_and_strangers(self, _):
        resp = self.client.post("/gc-admin/oauth/token", environ_base=ANTHROPIC_IP, data={"grant_type": "x", "client_id": "z"})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(self.client.post("/gc-admin/oauth/token", data={}).status_code, 404)


class McpEndpointTests(Base):
    def rpc(self, method, params=None, msg_id=1, token="good"):
        message = {"jsonrpc": "2.0", "method": method}
        if msg_id is not None:
            message["id"] = msg_id
        if params is not None:
            message["params"] = params
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        with patch("blueprints.admin.connector.oauth.check_access_token",
                   side_effect=lambda t: {"id": 1} if t == "good" else None), \
             patch("blueprints.admin.connector.local_today", return_value=TODAY):
            return self.client.post("/gc-admin/mcp", json=message, headers=headers, environ_base=ANTHROPIC_IP)

    def test_no_token_starts_sign_in(self):
        resp = self.rpc("initialize", {}, token=None)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.headers["WWW-Authenticate"],
                         'Bearer resource_metadata="https://glad.codes/.well-known/oauth-protected-resource/gc-admin/mcp", scope="devotion"')
        bad = self.rpc("initialize", {}, token="stolen")
        self.assertIn('error="invalid_token"', bad.headers["WWW-Authenticate"])

    def test_only_anthropic_networks(self):
        resp = self.client.post("/gc-admin/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(resp.status_code, 404)

    def test_initialize_and_list_tools(self):
        init = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}}).get_json()
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", init["result"]["capabilities"])
        newer = self.rpc("initialize", {"protocolVersion": "2099-01-01"}).get_json()
        self.assertEqual(newer["result"]["protocolVersion"], mcp_server.PROTOCOL_VERSIONS[0])
        self.assertEqual(self.rpc("notifications/initialized", msg_id=None).status_code, 202)
        tools = self.rpc("tools/list").get_json()["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["save_prayer", "save_devotion", "get_day", "get_bible_progress"])
        self.assertNotIn("delete", json.dumps(tools).lower().replace("can't delete", ""))

    def test_get_is_not_a_stream(self):
        with patch("blueprints.admin.connector.oauth.check_access_token", return_value={"id": 1}):
            resp = self.client.get("/gc-admin/mcp", headers={"Authorization": "Bearer good"}, environ_base=ANTHROPIC_IP)
        self.assertEqual(resp.status_code, 405)

    @patch("services.mcp_server.devotion.save_prayer", return_value={"saved": True, "added": False})
    def test_save_prayer_word_for_word(self, mock_save):
        spoken = "Lord, um, um, salamat po "
        resp = self.rpc("tools/call", {"name": "save_prayer", "arguments": {
            "date": "2026-11-12", "part": "evening", "prayer_text": spoken}}).get_json()
        mock_save.assert_called_once_with(date(2026, 11, 12), "evening", spoken, "ask")
        self.assertFalse(resp["result"]["isError"])
        self.assertTrue(resp["result"]["structuredContent"]["saved"])

    @patch("services.mcp_server.devotion.save_prayer", return_value={"saved": False, "needs_choice": True, "existing": "Old"})
    def test_existing_prayer_tells_claude_to_ask(self, _):
        result = self.rpc("tools/call", {"name": "save_prayer", "arguments": {
            "part": "morning", "prayer_text": "New"}}).get_json()["result"]["structuredContent"]
        self.assertTrue(result["needs_choice"])
        self.assertEqual(result["existing_prayer"], "Old")
        self.assertIn("Ask Glad", result["message"])
        self.assertEqual(result["date"], "2026-11-13")  # defaults to today

    @patch("services.mcp_server.devotion.save_devotion",
           return_value={"saved": True, "added": False, "bible_passage": "Psalm 37", "chapters": 1})
    def test_save_devotion(self, mock_save):
        graphic = {"title": "Waiting on God"}
        result = self.rpc("tools/call", {"name": "save_devotion", "arguments": {
            "chapters": "Psalm 37", "written_devotion": "# D", "infographic": graphic,
            "if_exists": "replace"}}).get_json()["result"]
        mock_save.assert_called_once_with(TODAY, "Psalm 37", "# D", graphic, "replace")
        self.assertEqual(result["structuredContent"]["chapters_recorded"], 1)

    def test_bad_input_is_a_tool_error_not_a_crash(self):
        result = self.rpc("tools/call", {"name": "save_prayer", "arguments": {
            "date": "2026-11-14", "part": "morning", "prayer_text": "x"}}).get_json()["result"]
        self.assertTrue(result["isError"])
        self.assertIn("future", result["content"][0]["text"])
        result = self.rpc("tools/call", {"name": "save_prayer", "arguments": {
            "date": "13/11/2026", "part": "morning", "prayer_text": "x"}}).get_json()["result"]
        self.assertTrue(result["isError"])
        unknown = self.rpc("tools/call", {"name": "delete_day", "arguments": {}}).get_json()
        self.assertEqual(unknown["error"]["code"], -32602)

    @patch("services.mcp_server.devotion.bible_progress", return_value={
        "covered": 7, "total": 1189, "percent": 0.6, "books_started": 5, "books_finished": 0, "by_book": {"Psalms": [37, 51]}})
    @patch("services.mcp_server.devotion.get_day", return_value={"date": "2026-11-13", "morning_prayer": "P"})
    def test_read_tools(self, mock_day, _):
        day = self.rpc("tools/call", {"name": "get_day", "arguments": {"date": "2026-11-13"}}).get_json()
        mock_day.assert_called_once_with(TODAY)
        self.assertEqual(day["result"]["structuredContent"]["morning_prayer"], "P")
        progress = self.rpc("tools/call", {"name": "get_bible_progress", "arguments": {}}).get_json()
        self.assertEqual(progress["result"]["structuredContent"]["chapters_covered"], 7)

    def test_unknown_method_and_garbage(self):
        self.assertEqual(self.rpc("resources/list").get_json()["error"]["code"], -32601)
        with patch("blueprints.admin.connector.oauth.check_access_token", return_value={"id": 1}):
            resp = self.client.post("/gc-admin/mcp", data="not json", content_type="application/json",
                                    headers={"Authorization": "Bearer good"}, environ_base=ANTHROPIC_IP)
        self.assertEqual(resp.status_code, 400)

    def test_crash_does_not_leak_prayer_text(self):
        with patch("services.mcp_server.devotion.save_prayer", side_effect=RuntimeError("Lord, secret prayer")), \
             self.assertLogs("blueprints.admin.connector", level="ERROR") as logs:
            resp = self.rpc("tools/call", {"name": "save_prayer", "arguments": {"part": "morning", "prayer_text": "x"}})
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn("secret prayer", resp.get_data(as_text=True))
        self.assertNotIn("secret prayer", "\n".join(logs.output))


class DisconnectTests(Base):
    @patch("blueprints.admin.connector.oauth.revoke_all")
    def test_disconnect_needs_session_and_csrf(self, mock_revoke):
        resp = self.client.post("/gc-admin/connectors/claude/disconnect")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/gc-admin/login", resp.headers["Location"])
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))
        self.client.set_cookie(CSRF_COOKIE_NAME, "t")
        resp = self.client.post("/gc-admin/connectors/claude/disconnect", data={"csrf_token": "t"})
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/connectors/claude"))
        mock_revoke.assert_called_once()


class ConnectorPageTests(Base):
    def test_claude_connector_page(self):
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))
        with patch("blueprints.admin.connector.oauth.connection_status", return_value={"connected": True, "last_used": None}):
            body = self.client.get("/gc-admin/connectors/claude").get_data(as_text=True)
        self.assertIn("https://glad.codes/gc-admin/mcp", body)
        self.assertIn("connector-state is-on", body)
        self.assertIn("/gc-admin/connectors/claude/disconnect", body)


class PublicPagesNeverMentionConnector(Base):
    def test_robots_and_sitemap_do_not_leak(self):
        for path in ("/robots.txt", "/sitemap.xml"):
            with patch("blueprints.public.routes.query", return_value=[]):
                body = self.client.get(path).get_data(as_text=True)
            self.assertNotIn("oauth", body)
            self.assertNotIn("mcp", body)


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app import create_app
from blueprints.admin import mfa as gate
from blueprints.admin.auth import COOKIE_NAME, PENDING_COOKIE, issue_pending_token, issue_token, verify_token
from blueprints.admin.csrf import CSRF_COOKIE_NAME
from services import mfa as mfa_service
from services import totp

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890", RFC 6238 test key


class TotpTests(unittest.TestCase):
    def test_rfc6238_vectors(self):
        # RFC 6238 appendix B (SHA-1), last 6 of the 8-digit values.
        self.assertEqual(totp.match(RFC_SECRET, "287082", now=59, window=0), 1)
        self.assertEqual(totp.match(RFC_SECRET, "081804", now=1111111109, window=0), 37037036)
        self.assertEqual(totp.match(RFC_SECRET, "050471", now=1111111111, window=0), 37037037)

    def test_drift_window_and_junk(self):
        self.assertEqual(totp.match(RFC_SECRET, "287 082", now=59 + 30), 1)  # one step late, spaces ok
        self.assertIsNone(totp.match(RFC_SECRET, "287082", now=59 + 90))
        self.assertIsNone(totp.match(RFC_SECRET, "12345", now=59))
        self.assertIsNone(totp.match("", "287082", now=59))

    def test_new_secret_and_uri(self):
        secret = totp.new_secret()
        self.assertEqual(len(secret), 32)
        uri = totp.provisioning_uri(secret, "glad")
        self.assertTrue(uri.startswith("otpauth://totp/GladCodes%3Aglad?"))
        self.assertIn("secret=" + secret, uri)


class SessionStateTests(unittest.TestCase):
    ENABLED = datetime(2026, 11, 16, 12, 0)

    def payload(self, issued):
        return {"sub": "glad", "iat": int(issued.replace(tzinfo=timezone.utc).timestamp())}

    def test_off_means_ok(self):
        with patch.object(gate.mfa_service, "enabled_at", return_value=None):
            self.assertEqual(gate.session_state(self.payload(self.ENABLED), None), "ok")

    def test_devices_signed_in_before_mfa_get_registered(self):
        with patch.object(gate.mfa_service, "enabled_at", return_value=self.ENABLED):
            self.assertEqual(gate.session_state(self.payload(self.ENABLED - timedelta(days=3)), None), "trust")
            # A newer session without a device cookie skipped the code step.
            self.assertEqual(gate.session_state(self.payload(self.ENABLED + timedelta(minutes=1)), None), "deny")

    def test_removed_device_is_signed_out(self):
        with patch.object(gate.mfa_service, "enabled_at", return_value=self.ENABLED), \
             patch.object(gate.mfa_service, "device_trusted", return_value=False):
            self.assertEqual(gate.session_state(self.payload(self.ENABLED - timedelta(days=3)), "old-token"), "deny")
        with patch.object(gate.mfa_service, "enabled_at", return_value=self.ENABLED), \
             patch.object(gate.mfa_service, "device_trusted", return_value=True):
            self.assertEqual(gate.session_state(self.payload(self.ENABLED + timedelta(days=3)), "good"), "ok")


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.client.set_cookie(CSRF_COOKIE_NAME, "t")

    def cookies(self, resp):
        return {h.split("=", 1)[0]: h for h in resp.headers.getlist("Set-Cookie")}

    def test_pending_token_is_never_a_session(self):
        with self.app.app_context():
            self.assertIsNone(verify_token(issue_pending_token("glad", True)))
            self.assertIsNotNone(verify_token(issue_token("glad")))

    @patch("blueprints.admin.routes.is_rate_limited", return_value=False)
    @patch("blueprints.admin.routes.verify_credentials", return_value=True)
    @patch("blueprints.admin.routes.clear_attempts")
    @patch("blueprints.admin.routes.needs_code", return_value=True)
    def test_new_device_goes_to_code_step(self, *_):
        resp = self.client.post("/gc-admin/login", data={"csrf_token": "t", "username": "glad", "password": "pw",
                                                         "remember": "1"})
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/login/verify"))
        cookies = self.cookies(resp)
        self.assertIn(PENDING_COOKIE, cookies)
        self.assertNotIn(COOKIE_NAME, cookies)  # no session until the code
        self.assertIn("HttpOnly", cookies[PENDING_COOKIE])

    @patch("blueprints.admin.routes.is_rate_limited", return_value=False)
    @patch("blueprints.admin.routes.verify_credentials", return_value=True)
    @patch("blueprints.admin.routes.clear_attempts")
    @patch("blueprints.admin.routes.needs_code", return_value=False)
    def test_trusted_device_skips_code(self, *_):
        resp = self.client.post("/gc-admin/login", data={"csrf_token": "t", "username": "glad", "password": "pw"})
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/me"))
        self.assertIn(COOKIE_NAME, self.cookies(resp))

    def test_code_step_without_password_step_goes_to_login(self):
        resp = self.client.get("/gc-admin/login/verify")
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/login"))

    def start_pending(self, remember=True):
        with self.app.app_context():
            self.client.set_cookie(PENDING_COOKIE, issue_pending_token("glad", remember))

    @patch("blueprints.admin.mfa.is_rate_limited", return_value=False)
    @patch("blueprints.admin.mfa.clear_attempts")
    @patch("blueprints.admin.mfa.mfa_service.trust_device", return_value="DEVICE-TOKEN")
    @patch("blueprints.admin.mfa.mfa_service.verify_code", return_value=True)
    def test_right_code_signs_in_and_trusts_device(self, verify, trust, *_):
        self.start_pending()
        resp = self.client.post("/gc-admin/login/verify", data={"csrf_token": "t", "code": "123456"},
                                headers={"User-Agent": "Mozilla/5.0 (Linux; Android 15) Chrome/140.0 Mobile"})
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/me"))
        cookies = self.cookies(resp)
        self.assertIn(COOKIE_NAME, cookies)
        self.assertIn(f"Max-Age={30 * 24 * 3600}", cookies[COOKIE_NAME])  # remember carried through
        self.assertIn("gc_device=DEVICE-TOKEN", cookies["gc_device"])
        self.assertIn("HttpOnly", cookies["gc_device"])
        verify.assert_called_once_with("glad", "123456")
        trust.assert_called_once_with("glad", "Chrome on Android")

    @patch("blueprints.admin.mfa.is_rate_limited", return_value=False)
    @patch("blueprints.admin.mfa.record_failed_attempt")
    @patch("blueprints.admin.mfa.mfa_service.verify_code", return_value=False)
    def test_wrong_code_is_counted(self, _, record, __):
        self.start_pending()
        resp = self.client.post("/gc-admin/login/verify", data={"csrf_token": "t", "code": "000000"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("work", resp.get_data(as_text=True))
        self.assertNotIn(COOKIE_NAME, self.cookies(resp))
        record.assert_called_once_with("127.0.0.1", "glad")

    @patch("blueprints.admin.mfa.is_rate_limited", return_value=True)
    @patch("blueprints.admin.mfa.mfa_service.verify_code")
    def test_code_step_is_rate_limited(self, verify, _):
        self.start_pending()
        body = self.client.post("/gc-admin/login/verify", data={"csrf_token": "t", "code": "1"}).get_data(as_text=True)
        self.assertIn("Too many attempts", body)
        self.assertFalse(verify.called)

    @patch("blueprints.admin.mfa.session_state", return_value="trust")
    @patch("blueprints.admin.mfa.mfa_service.trust_device", return_value="NEW-DEVICE")
    def test_signed_in_device_is_registered_automatically(self, trust, _):
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))
        with patch("blueprints.admin.connector.oauth.connection_status",
                   return_value={"connected": False, "last_used": None}):
            resp = self.client.get("/gc-admin/connectors/claude")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("gc_device=NEW-DEVICE", self.cookies(resp)["gc_device"])
        trust.assert_called_once()

    @patch("blueprints.admin.mfa.session_state", return_value="deny")
    def test_denied_session_is_silently_sent_to_login(self, _):
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))
        resp = self.client.get("/gc-admin/me")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/login"))


class ServiceTests(unittest.TestCase):
    """Replay guard and one-time recovery codes, with the DB mocked."""

    def setUp(self):
        self.app = create_app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.addCleanup(self.ctx.pop)

    def user(self, **extra):
        return dict({"id": 1, "username": "glad", "totp_secret": RFC_SECRET, "totp_pending_secret": None,
                     "totp_enabled_at": datetime(2026, 1, 1), "totp_last_counter": 0}, **extra)

    def fake_transaction(self, rowcount):
        cursor = MagicMock(rowcount=rowcount)
        cm = MagicMock()
        cm.__enter__.return_value = cursor
        return cm, cursor

    def test_code_used_twice_is_refused(self):
        cm, cursor = self.fake_transaction(rowcount=0)  # counter already moved past it
        with patch.object(mfa_service, "_user", return_value=self.user()), \
             patch.object(mfa_service, "transaction", return_value=cm), \
             patch.object(mfa_service.totp, "match", return_value=55):
            self.assertFalse(mfa_service.verify_code("glad", "123456"))
        sql, params = cursor.execute.call_args[0]
        self.assertIn("totp_last_counter < %s", sql)
        self.assertEqual(params, (55, 1, 55))

    def test_recovery_code_is_hashed_and_burned(self):
        cm, cursor = self.fake_transaction(rowcount=1)
        with patch.object(mfa_service, "_user", return_value=self.user()), \
             patch.object(mfa_service, "transaction", return_value=cm), \
             patch.object(mfa_service.totp, "match", return_value=None):
            self.assertTrue(mfa_service.verify_code("glad", "A1B2C3-D4E5F6"))
        sql, params = cursor.execute.call_args[0]
        self.assertIn("used_at IS NULL", sql)
        self.assertEqual(params[2], mfa_service._hash("a1b2c3d4e5f6"))
        self.assertNotIn("a1b2c3d4e5f6", str(params))

    def test_off_means_no_code_accepted(self):
        with patch.object(mfa_service, "_user", return_value=self.user(totp_secret=None)):
            self.assertFalse(mfa_service.verify_code("glad", "287082"))

    def test_device_labels(self):
        self.assertEqual(gate.device_label("Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/140 Safari/537 Edg/140"),
                         "Edge on Windows")
        self.assertEqual(gate.device_label("Mozilla/5.0 (Linux; Android 15) SamsungBrowser/28 Chrome/130"),
                         "Samsung Internet on Android")
        self.assertEqual(gate.device_label(""), "Browser")


if __name__ == "__main__":
    unittest.main()

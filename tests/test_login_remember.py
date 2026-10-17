import unittest
from unittest.mock import patch

import jwt

from app import create_app
from blueprints.admin.auth import COOKIE_NAME
from blueprints.admin.csrf import CSRF_COOKIE_NAME


class RememberDeviceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")

    def _login(self, **extra):
        with patch("blueprints.admin.routes.verify_credentials", return_value=True), \
             patch("blueprints.admin.routes.is_rate_limited", return_value=False), \
             patch("blueprints.admin.routes.clear_attempts"), \
             patch("blueprints.admin.routes.has_checked_in", return_value=True):
            resp = self.client.post("/gc-admin/login", data=dict(
                {"csrf_token": "test-csrf", "username": "glad", "password": "pw"}, **extra))
        cookie = next(h for h in resp.headers.getlist("Set-Cookie") if h.startswith(COOKIE_NAME + "="))
        token = cookie.split(";", 1)[0].split("=", 1)[1]
        payload = jwt.decode(token, self.app.config["JWT_SECRET"], algorithms=["HS256"])
        return cookie, payload["exp"] - payload["iat"]

    def test_default_session_is_short(self):
        cookie, lifetime = self._login()
        self.assertEqual(lifetime, 30 * 60)
        self.assertIn("Max-Age=1800", cookie)

    def test_remember_this_device_lasts_30_days(self):
        cookie, lifetime = self._login(remember="1")
        self.assertEqual(lifetime, 30 * 24 * 60 * 60)
        self.assertIn(f"Max-Age={30 * 24 * 60 * 60}", cookie)
        self.assertIn("HttpOnly", cookie)


if __name__ == "__main__":
    unittest.main()

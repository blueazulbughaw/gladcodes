import unittest
from unittest.mock import patch

from app import create_app


class SecurityHeaderTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def assert_headers(self, resp):
        self.assertEqual(resp.headers["X-Frame-Options"], "DENY")
        self.assertEqual(resp.headers["Content-Security-Policy"], "frame-ancestors 'none'")
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp.headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertTrue(resp.headers["Strict-Transport-Security"].startswith("max-age=31536000"))
        self.assertIn("camera=()", resp.headers["Permissions-Policy"])

    def test_admin_login_and_redirects_carry_headers(self):
        self.assert_headers(self.client.get("/gc-admin/login"))
        self.assert_headers(self.client.get("/gc-admin/me"))  # silent redirect to login

    def test_public_pages_and_errors_carry_headers(self):
        self.assert_headers(self.client.get("/robots.txt"))
        self.assert_headers(self.client.get("/no-such-page-here"))

    def test_oauth_approval_page_cannot_be_framed(self):
        with patch("blueprints.admin.connector.oauth.get_client", return_value=None):
            resp = self.client.get("/gc-admin/oauth/authorize?client_id=x")
        self.assertEqual(resp.headers["X-Frame-Options"], "DENY")


if __name__ == "__main__":
    unittest.main()

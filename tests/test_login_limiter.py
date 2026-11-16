import unittest
from unittest.mock import patch

from app import create_app
from blueprints.admin import auth
from blueprints.admin.csrf import CSRF_COOKIE_NAME


class LoginLimiterTests(unittest.TestCase):
    """Failed sign-ins are counted in the DB so every Passenger worker shares them."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.client.set_cookie(CSRF_COOKIE_NAME, "t")

    def count(self, by_ip, by_user):
        return lambda sql, params: {"n": by_ip if "ip = %s" in sql else by_user}

    def test_limits_per_ip_and_per_username(self):
        with self.app.app_context():
            with patch("blueprints.admin.auth.query_one", side_effect=self.count(4, 0)):
                self.assertFalse(auth.is_rate_limited("1.2.3.4", "glad"))
            with patch("blueprints.admin.auth.query_one", side_effect=self.count(5, 0)):
                self.assertTrue(auth.is_rate_limited("1.2.3.4", "glad"))
            # Spread over many IPs: the username total still trips.
            with patch("blueprints.admin.auth.query_one", side_effect=self.count(1, 20)):
                self.assertTrue(auth.is_rate_limited("5.6.7.8", "glad"))
            with patch("blueprints.admin.auth.query_one", side_effect=self.count(1, 19)):
                self.assertFalse(auth.is_rate_limited("5.6.7.8", "glad"))

    def test_record_is_parameterized_and_prunes_old_rows(self):
        with self.app.app_context(), patch("blueprints.admin.auth.execute") as mock_execute:
            auth.record_failed_attempt("1.2.3.4", "x" * 500)
        insert, prune = mock_execute.call_args_list
        self.assertIn("INSERT INTO login_attempts", insert[0][0])
        self.assertEqual(insert[0][1][:2], ("1.2.3.4", "x" * 100))
        self.assertIn("DELETE FROM login_attempts WHERE attempted_at <", prune[0][0])

    def test_login_route_blocks_without_checking_password(self):
        with patch("blueprints.admin.routes.is_rate_limited", return_value=True) as limited, \
             patch("blueprints.admin.routes.verify_credentials") as verify:
            body = self.client.post("/gc-admin/login", data={
                "csrf_token": "t", "username": "glad", "password": "guess"}).get_data(as_text=True)
        self.assertIn("Too many attempts", body)
        self.assertFalse(verify.called)
        limited.assert_called_once_with("127.0.0.1", "glad")

    def test_failed_login_is_recorded_with_username(self):
        with patch("blueprints.admin.routes.is_rate_limited", return_value=False), \
             patch("blueprints.admin.routes.verify_credentials", return_value=False), \
             patch("blueprints.admin.routes.record_failed_attempt") as record:
            self.client.post("/gc-admin/login", data={"csrf_token": "t", "username": "glad", "password": "x"})
        record.assert_called_once_with("127.0.0.1", "glad")


if __name__ == "__main__":
    unittest.main()

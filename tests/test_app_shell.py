import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from app import create_app
from blueprints.admin.auth import COOKIE_NAME, issue_token
from blueprints.admin.csrf import CSRF_COOKIE_NAME
from send_reminders import due_reminder, reminder_text

EVENING_EMPTY = {"win": None, "focus": None, "priority_done": 0, "scroll_minutes": None, "top_priority": "Ship push"}
EVENING_DONE = dict(EVENING_EMPTY, win="Shipped it")


class InstallableAppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.anon = self.app.test_client()
        self.client = self.app.test_client()
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")

    def test_manifest_and_sw_load_without_a_session(self):
        resp = self.anon.get("/gc-admin/manifest.webmanifest")
        self.assertEqual(resp.status_code, 200)
        manifest = json.loads(resp.get_data(as_text=True))
        self.assertEqual(manifest["start_url"], "/gc-admin/today")
        self.assertEqual(manifest["scope"], "/gc-admin/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(resp.headers["X-Robots-Tag"], "noindex, nofollow")

        sw = self.anon.get("/gc-admin/sw.js")
        self.assertEqual(sw.status_code, 200)
        self.assertIn("javascript", sw.headers["Content-Type"])
        self.assertIn('addEventListener("push"', sw.get_data(as_text=True))

    def test_login_page_stays_bare(self):
        body = self.anon.get("/gc-admin/login").get_data(as_text=True)
        self.assertNotIn("manifest", body)
        self.assertNotIn("serviceWorker", body)

    def test_push_endpoints_still_require_login(self):
        resp = self.anon.post("/gc-admin/push/subscribe", data={"endpoint": "https://x"})
        self.assertEqual(resp.status_code, 302)

    @patch("blueprints.admin.app_shell.save_subscription")
    def test_subscribe_validates_and_saves(self, mock_save):
        bad = self.client.post("/gc-admin/push/subscribe", data={"csrf_token": "test-csrf", "endpoint": "http://insecure", "p256dh": "k", "auth": "a"})
        self.assertEqual(bad.status_code, 400)
        mock_save.assert_not_called()
        ok = self.client.post("/gc-admin/push/subscribe", data={
            "csrf_token": "test-csrf", "endpoint": "https://fcm.googleapis.com/fcm/send/abc", "p256dh": "key", "auth": "secret"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(mock_save.call_args[0][:3], ("https://fcm.googleapis.com/fcm/send/abc", "key", "secret"))

    def test_subscribe_without_csrf_is_rejected(self):
        resp = self.client.post("/gc-admin/push/subscribe", data={"endpoint": "https://x", "p256dh": "k", "auth": "a"})
        self.assertEqual(resp.status_code, 400)


class ReminderScheduleTests(unittest.TestCase):
    def test_morning_only_when_not_checked_in(self):
        self.assertEqual(due_reminder(8, 8, 21, None), "morning")
        self.assertIsNone(due_reminder(8, 8, 21, EVENING_EMPTY))

    def test_evening_only_when_evening_half_is_empty(self):
        self.assertEqual(due_reminder(21, 8, 21, EVENING_EMPTY), "evening")
        self.assertEqual(due_reminder(21, 8, 21, None), "evening")
        self.assertIsNone(due_reminder(21, 8, 21, EVENING_DONE))

    def test_quiet_at_other_hours(self):
        self.assertIsNone(due_reminder(13, 8, 21, None))

    def test_evening_text_names_the_priority(self):
        self.assertIn("Ship push", reminder_text("evening", EVENING_EMPTY)[1])


class VapidKeyTests(unittest.TestCase):
    def test_generated_keys_load_in_pywebpush(self):
        from py_vapid import Vapid

        out = subprocess.run([sys.executable, "generate_vapid_keys.py"], capture_output=True, text=True, check=True).stdout
        keys = dict(line.split("=", 1) for line in out.strip().splitlines())
        vapid = Vapid.from_string(keys["VAPID_PRIVATE_KEY"])
        self.assertIsNotNone(vapid.private_key)
        self.assertEqual(len(keys["VAPID_PUBLIC_KEY"]), 87)  # 65 raw bytes, base64url


if __name__ == "__main__":
    unittest.main()

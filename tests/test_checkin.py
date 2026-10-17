import unittest
from datetime import date, datetime
from unittest.mock import patch

from app import create_app
from blueprints.admin.auth import COOKIE_NAME, issue_token
from blueprints.admin.checkin import current_streak, parse_day
from blueprints.admin.csrf import CSRF_COOKIE_NAME
from services.github import bucket_pushes_by_week

TODAY = date(2026, 10, 16)  # a Friday


class CheckinHelperTests(unittest.TestCase):
    def test_streak_counts_back_from_today(self):
        dates = [date(2026, 10, 16), date(2026, 10, 15), date(2026, 10, 14), date(2026, 10, 12)]
        self.assertEqual(current_streak(dates, TODAY), 3)

    def test_streak_survives_until_todays_checkin(self):
        # Morning, not checked in yet: yesterday's run still counts.
        self.assertEqual(current_streak([date(2026, 10, 15), date(2026, 10, 14)], TODAY), 2)

    def test_streak_breaks_after_a_missed_day(self):
        self.assertEqual(current_streak([date(2026, 10, 14)], TODAY), 0)

    def test_parse_day_rejects_garbage_and_future(self):
        self.assertEqual(parse_day("2026-10-01", TODAY), date(2026, 10, 1))
        self.assertEqual(parse_day("2026-12-25", TODAY), TODAY)
        self.assertEqual(parse_day("nope", TODAY), TODAY)
        self.assertEqual(parse_day(None, TODAY), TODAY)


class GithubActivityTests(unittest.TestCase):
    def test_buckets_pushes_into_weeks(self):
        events = [
            {"type": "PushEvent", "created_at": "2026-10-15T10:00:00Z", "repo": {"name": "glad/gladcodes"}},
            {"type": "PushEvent", "created_at": "2026-10-12T09:00:00Z", "repo": {"name": "glad/other"}},
            {"type": "PushEvent", "created_at": "2026-10-08T09:00:00Z", "repo": {"name": "glad/other"}},
            {"type": "WatchEvent", "created_at": "2026-10-15T11:00:00Z", "repo": {"name": "x/y"}},
            {"type": "PushEvent", "created_at": "2025-01-01T00:00:00Z", "repo": {"name": "old/repo"}},
        ]
        result = bucket_pushes_by_week(events, TODAY, weeks=3)
        self.assertEqual(result["labels"], ["Sep 28", "Oct 05", "Oct 12"])
        self.assertEqual(result["data"], [0, 1, 2])
        self.assertEqual(result["pushes_30d"], 3)
        self.assertEqual(result["last_push"]["repo"], "glad/gladcodes")
        self.assertNotIn("values", result)  # see CLAUDE.md: Jinja's dict.values trap


class TodayPageTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            token = issue_token("glad")
        self.client.set_cookie(COOKIE_NAME, token)
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")

    @patch("blueprints.admin.checkin.get_weekly_activity", return_value=None)
    @patch("blueprints.admin.checkin.configured_username", return_value=None)
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 7, 30))
    @patch("blueprints.admin.checkin.query_one")
    @patch("blueprints.admin.checkin.query")
    def test_today_page_renders_with_history(self, mock_query, mock_query_one, *_):
        mock_query_one.return_value = {"mood": 4, "energy": 3, "focus": None, "sleep_hours": 7.5,
                                       "took_meds": 1, "exercised": 0, "reading": "Designing Data-Intensive Apps",
                                       "grateful": "Coffee", "top_priority": "Ship check-in", "priority_done": 0,
                                       "scroll_minutes": None, "win": None, "notes": None}
        mock_query.side_effect = lambda sql, *a: (
            [{"checkin_date": TODAY, "mood": 4, "reading": "DDIA", "grateful": "Coffee",
              "top_priority": "Ship check-in", "priority_done": 0, "win": None,
              "energy": 3, "focus": None, "sleep_hours": 7.5, "scroll_minutes": 20}]
        )
        resp = self.client.get("/gc-admin/today")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn("Good morning, Glad", body)
        self.assertIn("1-day streak", body)
        self.assertIn("Designing Data-Intensive Apps", body)
        self.assertIn('name="robots" content="noindex, nofollow"', body)

    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 7, 30))
    @patch("blueprints.admin.checkin.execute")
    def test_post_upserts_and_sanitizes(self, mock_execute, _):
        resp = self.client.post("/gc-admin/today", data={
            "csrf_token": "test-csrf", "checkin_date": "2026-10-16",
            "mood": "9", "energy": "4", "sleep_hours": "30", "took_meds": "1",
            "reading": "  Atomic Habits  ", "scroll_minutes": "45",
        })
        self.assertEqual(resp.status_code, 302)
        params = mock_execute.call_args[0][1]
        self.assertEqual(params[0], TODAY)
        self.assertIsNone(params[1])        # mood 9 is out of range
        self.assertEqual(params[2], 4)      # energy
        self.assertIsNone(params[4])        # 30 hours of sleep rejected
        self.assertEqual(params[5], 1)      # took_meds
        self.assertEqual(params[7], "Atomic Habits")
        self.assertEqual(params[11], 45)

    def test_today_requires_login_silently(self):
        anon = self.app.test_client()
        resp = anon.get("/gc-admin/today")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/login"))


if __name__ == "__main__":
    unittest.main()

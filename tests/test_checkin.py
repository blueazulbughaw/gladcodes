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


class SectionPageTests(unittest.TestCase):
    """The daily inputs, one page per section (checkin.SECTIONS)."""

    ENTRY = {
        "mood": 4, "mood_reason": "Slept well", "energy": 3, "morning_prayer": 1, "night_prayer": 0,
        "exercised": 0, "period_day": 0, "reading": "DDIA", "bible_passage": "Psalm 23",
        "grateful": "Coffee", "learnings": "Flask url_defaults", "win": None, "notes": None,
        "morning_prayer_note": "Lord, guide my work today.", "water_glasses": 3,
        "night_prayer_note": "Thank you for this day.", "devotion_thoughts": "Rest in Him.",
        "food_breakfast": "Oatmeal", "food_lunch": "Rice bowl", "food_dinner": None, "food_snacks": "Mango",
    }

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            token = issue_token("glad")
        self.client.set_cookie(COOKIE_NAME, token)
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")

    def render(self, path, entry=ENTRY):
        from services import tracking as real
        with patch("blueprints.admin.checkin.local_tz_name", return_value="UTC"), \
             patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 7, 30)), \
             patch("blueprints.admin.checkin.query", return_value=[]), \
             patch("blueprints.admin.checkin.query_one", return_value=entry) as q1, \
             patch("blueprints.admin.checkin.tracking") as t:
            t.active_medications.return_value = [
                {"id": 7, "name": "Vitamin D", "notes": "with food", "frequency": "daily", "doses_per_day": 3, "start_date": None},
                {"id": 8, "name": "Weekly pill", "notes": None, "frequency": "weekly", "doses_per_day": 1, "start_date": date(2026, 10, 14)},
            ]
            t.doses_taken.return_value = {(7, TODAY): {1}}
            t.medication_due.side_effect = real.medication_due
            t.dose_count.side_effect = real.dose_count
            t.sleep_by_day.return_value = {TODAY: 435}
            t.app_minutes_by_day.return_value = {TODAY: 23}
            t.tracking_status.return_value = {"last_sleep": {"x": 1}, "last_app": None}
            t.TRACKED_APP = "Instagram"
            resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        return resp.get_data(as_text=True), q1

    def test_prayer_page(self):
        body, _ = self.render("/gc-admin/prayer")
        order = ["> Morning</h2>", "> Devotion</h2>", "> Evening</h2>"]
        self.assertEqual([body.index(h) for h in order], sorted(body.index(h) for h in order))
        for text in ("Lord, guide my work today.", "Psalm 23", "Thoughts on the devotion", "Rest in Him.",
                     "Thank you for this day.", "Saves automatically"):
            self.assertIn(text, body)
        self.assertNotIn('name="morning_prayer"', body)  # no prayer checkboxes, just the boxes
        for other in ("How are you feeling?", "Breakfast", "Vitamin D", "What did you read?"):
            self.assertNotIn(other, body)

    def test_emotions_page(self):
        body, _ = self.render("/gc-admin/emotions")
        for text in ("How are you feeling?", "Why do you feel that way?", "Slept well", "Energy",
                     "What are you thankful for today?", "Coffee"):
            self.assertIn(text, body)
        self.assertNotIn("My prayer", body)

    def test_body_page(self):
        body, _ = self.render("/gc-admin/body")
        for text in ("7h 15m", "23 min", "3 of 8 glasses", "Moved my body", "Period day", "Oatmeal", "Mango"):
            self.assertIn(text, body)
        self.assertEqual(body.count('name="water" value="'), 8)

    def test_medicine_page(self):
        body, _ = self.render("/gc-admin/medicine")
        self.assertIn("Vitamin D", body)
        self.assertNotIn("Weekly pill", body)  # due Wednesdays, today is Friday
        self.assertEqual(body.count('class="dose-box"'), 3)
        self.assertIn("/gc-admin/medications", body)  # edit the list

    def test_learnings_page(self):
        body, _ = self.render("/gc-admin/learnings")
        for text in ("What did you read?", "DDIA", "Learnings", "Flask url_defaults", "Wins", "Notes"):
            self.assertIn(text, body)
        self.assertIn("/gc-admin/app_ideas/create", body)

    @patch("blueprints.admin.checkin.saved_timezone", return_value=None)
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 7, 30))
    @patch("blueprints.admin.checkin.execute")
    def test_each_page_saves_only_its_own_boxes(self, mock_execute, *_):
        everything = {
            "csrf_token": "test-csrf", "checkin_date": "2026-10-16",
            "mood": "9", "energy": "4", "period_day": "1", "mood_reason": "  Good sleep  ",
            "bible_passage": "John 15", "learnings": "Jinja macros", "morning_prayer_note": "Thank you for today",
            "water": ["1", "2", "3", "3", "9"], "night_prayer_note": "Goodnight prayer", "devotion_thoughts": "Trust",
            "food_breakfast": " Eggs ", "food_snacks": "Nuts",
        }
        expected = {
            "prayer": {"morning_prayer_note": "Thank you for today", "morning_prayer": 1, "bible_passage": "John 15",
                       "devotion_thoughts": "Trust", "night_prayer_note": "Goodnight prayer", "night_prayer": 1},
            "emotions": {"mood": None, "mood_reason": "Good sleep", "energy": 4, "grateful": None},  # 9 is out of range
            "body": {"water_glasses": 3, "exercised": 0, "period_day": 1, "food_breakfast": "Eggs",
                     "food_lunch": None, "food_dinner": None, "food_snacks": "Nuts"},
            "learnings": {"reading": None, "learnings": "Jinja macros", "win": None, "notes": None},
        }
        for key, values in expected.items():
            resp = self.client.post(f"/gc-admin/{key}", headers={"X-Requested-With": "fetch"}, data=everything)
            self.assertEqual(resp.get_json(), {"ok": True}, key)
            sql, params = mock_execute.call_args[0]
            columns = sql.split("INSERT INTO daily_checkins (")[1].split(")")[0].split(", ")
            self.assertEqual(columns[0], "checkin_date")
            self.assertEqual(columns[-1], "updated_at")
            saved = dict(zip(columns[1:-1], params[1:len(columns) - 1]))
            self.assertEqual(saved, values, key)
            self.assertEqual(params[0], TODAY)

    @patch("blueprints.admin.checkin.saved_timezone", return_value=None)
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 7, 30))
    @patch("blueprints.admin.checkin.execute")
    def test_medicine_page_post_writes_nothing(self, mock_execute, *_):
        self.client.post("/gc-admin/medicine", headers={"X-Requested-With": "fetch"},
                         data={"csrf_token": "test-csrf", "checkin_date": "2026-10-16", "mood": "3"})
        self.assertFalse(mock_execute.called)

    @patch("blueprints.admin.checkin.saved_timezone", return_value=None)
    @patch("blueprints.admin.checkin.tracking.set_dose")
    def test_dose_checkbox_saves_and_validates(self, mock_set, _):
        ok = self.client.post("/gc-admin/today/dose", data={
            "csrf_token": "test-csrf", "checkin_date": "2026-10-16", "medication_id": "7", "dose_index": "2", "taken": "1"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(mock_set.call_args[0][0], 7)
        self.assertEqual(mock_set.call_args[0][2:], (2, True))
        bad = self.client.post("/gc-admin/today/dose", data={
            "csrf_token": "test-csrf", "medication_id": "7", "dose_index": "9", "taken": "1"})
        self.assertEqual(bad.status_code, 400)

    def test_past_day_can_be_opened_and_saves_to_that_day(self):
        body, q1 = self.render("/gc-admin/emotions?date=2026-10-14", entry=None)
        self.assertIn("You're editing <strong>Wednesday, October 14, 2026</strong>", body)
        self.assertIn('name="checkin_date" value="2026-10-14"', body)    # autosave posts this day
        self.assertIn('href="/gc-admin/emotions?date=2026-10-13"', body)  # previous day
        self.assertIn('href="/gc-admin/emotions?date=2026-10-15"', body)  # next day
        self.assertEqual(q1.call_args_list[0][0][1], (date(2026, 10, 14),))  # loads that day's entry

    def test_today_has_no_next_day_and_future_dates_clamp_to_today(self):
        body, _ = self.render("/gc-admin/body", entry=None)
        self.assertIn('checkin-daynav-step is-disabled', body)
        self.assertNotIn("You're editing", body)
        self.assertIn('max="2026-10-16"', body)
        future, _ = self.render("/gc-admin/body?date=2030-01-01", entry=None)
        self.assertIn('name="checkin_date" value="2026-10-16"', future)

    @patch("blueprints.admin.checkin.saved_timezone", return_value=None)
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 20, 0))
    @patch("blueprints.admin.checkin.execute")
    def test_autosave_for_a_past_day_writes_that_day(self, mock_execute, *_):
        self.client.post("/gc-admin/learnings", headers={"X-Requested-With": "fetch"},
                         data={"csrf_token": "test-csrf", "checkin_date": "2026-10-14", "win": "Remembered it"})
        params = mock_execute.call_args[0][1]
        self.assertEqual(params[0], date(2026, 10, 14))

    def test_old_today_url_goes_to_my_dashboard(self):
        resp = self.client.get("/gc-admin/today")
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/me"))
        resp = self.client.get("/gc-admin/today?date=2026-10-14")
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/me?d=2026-10-14"))

    def test_pages_require_login_silently(self):
        anon = self.app.test_client()
        for path in ("/gc-admin/today", "/gc-admin/prayer", "/gc-admin/body", "/gc-admin/connectors/claude"):
            resp = anon.get(path)
            self.assertEqual(resp.status_code, 302, path)
            self.assertTrue(resp.headers["Location"].endswith("/gc-admin/login"), path)


if __name__ == "__main__":
    unittest.main()

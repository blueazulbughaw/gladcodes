import unittest
from datetime import date, datetime
from unittest.mock import patch

from app import create_app
from blueprints.admin.auth import COOKIE_NAME, issue_token
from blueprints.admin.checkin import CHECKIN_FIELDS, current_streak, parse_day
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
    @patch("blueprints.admin.checkin.local_tz_name", return_value="America/New_York")
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 7, 30))
    @patch("blueprints.admin.checkin.tracking")
    @patch("blueprints.admin.checkin.query_one")
    @patch("blueprints.admin.checkin.query")
    def test_today_page_renders_new_fields(self, mock_query, mock_query_one, mock_tracking, *_):
        from services import tracking as real

        mock_query.return_value = [{"checkin_date": TODAY}]
        mock_query_one.return_value = {
            "mood": 4, "mood_reason": "Slept well", "energy": 3, "morning_prayer": 1, "night_prayer": 0,
            "exercised": 0, "period_day": 0, "reading": "DDIA", "bible_passage": "Psalm 23",
            "grateful": "Coffee", "learnings": "Flask url_defaults", "win": None, "notes": None,
            "morning_prayer_note": "Lord, guide my work today.", "water_glasses": 3,
            "night_prayer_note": "Thank you for this day.", "devotion_thoughts": "Rest in Him.",
        }
        mock_tracking.active_medications.return_value = [
            {"id": 7, "name": "Vitamin D", "notes": "with food", "frequency": "daily", "doses_per_day": 3, "start_date": None},
            {"id": 8, "name": "Weekly pill", "notes": None, "frequency": "weekly", "doses_per_day": 1, "start_date": date(2026, 10, 14)},
        ]
        mock_tracking.doses_taken.return_value = {(7, TODAY): {1}}
        mock_tracking.medication_due.side_effect = real.medication_due
        mock_tracking.dose_count.side_effect = real.dose_count
        mock_tracking.sleep_by_day.return_value = {TODAY: 435}
        mock_tracking.app_minutes_by_day.return_value = {TODAY: 23}
        mock_tracking.tracking_status.return_value = {"last_sleep": {"x": 1}, "last_app": None}
        mock_tracking.TRACKED_APP = "Instagram"

        resp = self.client.get("/gc-admin/today")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        for text in ("Good morning, Glad", "Morning prayer", "Night prayer", "Why do you feel that way?",
                     "Bible passage", "Psalm 23", "Thoughts on the devotion", "Learnings", "Flask url_defaults",
                     "Period day", "Vitamin D", "7h 15m", "23 min", "Saves automatically"):
            self.assertIn(text, body)
        self.assertNotIn("Weekly pill", body)  # due Wednesdays, today is Friday
        self.assertEqual(body.count('class="dose-box"'), 3)
        self.assertIn("Lord, guide my work today.", body)
        self.assertEqual(body.count('name="water" value="'), 8)
        self.assertIn("3 of 8 glasses", body)
        # Morning is prayer only; how you feel / why / energy / thankful are asked in the Evening.
        morning = body.split('data-lucide="sunrise"')[1].split("</section>")[0]
        evening = body.split('data-lucide="moon"></i> Evening')[1].split("</section>")[0]
        summary = body.split("My emotions</h2>")[1].split("</section>")[0]
        devotion = body.split("Devotion</h2>")[1].split("</section>")[0]
        learnings = body.split("Learnings</h2>")[1].split("</section>")[0]
        self.assertIn("Psalm 23", devotion)
        self.assertIn("Rest in Him.", devotion)
        for label in ("What did you read?", "Book, article, docs: anything counts", "Learnings", "Wins", "Notes"):
            self.assertIn(label, learnings)
        self.assertNotIn("Daily summary", body)
        # Devotion comes right after the morning prayer, before Medicine.
        self.assertLess(body.index("> Morning</h2>"), body.index("> Devotion</h2>"))
        self.assertLess(body.index("> Devotion</h2>"), body.index("> Medicine</h2>"))
        self.assertNotIn("Word &amp; learning", body)
        self.assertIn("My prayer", morning)
        self.assertIn("Night prayer", evening)
        self.assertIn("Thank you for this day.", evening)  # evening prayer box
        self.assertLess(body.index("> Evening</h2>"), body.index("My emotions</h2>"))
        self.assertNotIn("Wins", summary)
        self.assertNotIn("Notes", summary)
        for question in ("How are you feeling?", "Why do you feel that way?", "Energy", "What are you thankful for today?"):
            self.assertNotIn(question, morning)
            self.assertNotIn(question, evening)
            self.assertIn(question, summary)
        self.assertNotIn("Any app ideas today?", body)  # ideas are a list now, not a daily question
        self.assertIn("/gc-admin/app_ideas/create", body)
        self.assertNotIn("Hours slept", body)
        self.assertNotIn("Minutes scrolling", body)
        self.assertNotIn('type="submit" class="btn btn-primary">Save check-in', body)

    @patch("blueprints.admin.checkin.saved_timezone", return_value=None)
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 7, 30))
    @patch("blueprints.admin.checkin.execute")
    def test_autosave_post_returns_json_and_sanitizes(self, mock_execute, *_):
        resp = self.client.post("/gc-admin/today", headers={"X-Requested-With": "fetch"}, data={
            "csrf_token": "test-csrf", "checkin_date": "2026-10-16",
            "mood": "9", "energy": "4", "morning_prayer": "1", "period_day": "1",
            "mood_reason": "  Good sleep  ", "bible_passage": "John 15", "learnings": "Jinja macros",
            "morning_prayer_note": "Thank you for today", "water": ["1", "2", "3", "3", "9"],
            "night_prayer_note": "Goodnight prayer", "devotion_thoughts": "Trust",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"ok": True})
        params = mock_execute.call_args[0][1]
        fields = dict(zip(("checkin_date",) + CHECKIN_FIELDS, params))
        self.assertEqual(fields["checkin_date"], TODAY)
        self.assertIsNone(fields["mood"])            # 9 is out of range
        self.assertEqual(fields["energy"], 4)
        self.assertEqual(fields["mood_reason"], "Good sleep")
        self.assertEqual(fields["morning_prayer"], 1)
        self.assertEqual(fields["night_prayer"], 0)
        self.assertEqual(fields["period_day"], 1)
        self.assertEqual(fields["bible_passage"], "John 15")
        self.assertEqual(fields["learnings"], "Jinja macros")
        self.assertNotIn("app_ideas", fields)
        self.assertEqual(fields["morning_prayer_note"], "Thank you for today")
        self.assertEqual(fields["water_glasses"], 3)
        self.assertEqual(fields["night_prayer_note"], "Goodnight prayer")
        self.assertEqual(fields["devotion_thoughts"], "Trust")  # duplicates and out-of-range values ignored

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

    def _render(self, path):
        from services import tracking as real
        with patch("blueprints.admin.checkin.get_weekly_activity", return_value=None),              patch("blueprints.admin.checkin.configured_username", return_value=None),              patch("blueprints.admin.checkin.local_tz_name", return_value="UTC"),              patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 20, 0)),              patch("blueprints.admin.checkin.query", return_value=[]),              patch("blueprints.admin.checkin.query_one", return_value=None) as q1,              patch("blueprints.admin.checkin.tracking") as t:
            t.active_medications.return_value = []
            t.doses_taken.return_value = {}
            t.sleep_by_day.return_value = {}
            t.app_minutes_by_day.return_value = {}
            t.tracking_status.return_value = {"last_sleep": None, "last_app": None}
            t.TRACKED_APP = "Instagram"
            body = self.client.get(path).get_data(as_text=True)
        return body, q1

    def test_past_day_can_be_opened_and_saves_to_that_day(self):
        body, q1 = self._render("/gc-admin/today?date=2026-10-14")
        self.assertIn("You're editing <strong>Wednesday, October 14, 2026</strong>", body)
        self.assertIn('name="checkin_date" value="2026-10-14"', body)   # autosave posts this day
        self.assertIn('href="/gc-admin/today?date=2026-10-13"', body)  # previous day
        self.assertIn('href="/gc-admin/today?date=2026-10-15"', body)  # next day
        self.assertEqual(q1.call_args_list[0][0][1], (date(2026, 10, 14),))  # loads that day's entry

    def test_today_has_no_next_day_and_future_dates_clamp_to_today(self):
        body, _ = self._render("/gc-admin/today")
        self.assertIn('checkin-daynav-step is-disabled', body)
        self.assertNotIn("You're editing", body)
        self.assertIn('max="2026-10-16"', body)
        future, _ = self._render("/gc-admin/today?date=2030-01-01")
        self.assertIn('name="checkin_date" value="2026-10-16"', future)

    @patch("blueprints.admin.checkin.saved_timezone", return_value=None)
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 10, 16, 20, 0))
    @patch("blueprints.admin.checkin.execute")
    def test_autosave_for_a_past_day_writes_that_day(self, mock_execute, *_):
        self.client.post("/gc-admin/today", headers={"X-Requested-With": "fetch"},
                         data={"csrf_token": "test-csrf", "checkin_date": "2026-10-14", "win": "Remembered it"})
        params = mock_execute.call_args[0][1]
        self.assertEqual(params[0], date(2026, 10, 14))

    def test_today_requires_login_silently(self):
        anon = self.app.test_client()
        resp = anon.get("/gc-admin/today")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/login"))


if __name__ == "__main__":
    unittest.main()

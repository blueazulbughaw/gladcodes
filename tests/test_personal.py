import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from app import create_app
from blueprints.admin.auth import COOKIE_NAME, issue_token
from blueprints.admin.csrf import CSRF_COOKIE_NAME
from services import tracking

TODAY = date(2026, 10, 16)


class PeriodTests(unittest.TestCase):
    def test_runs_of_days_become_periods_and_bridge_one_forgotten_day(self):
        days = [date(2026, 8, 20), date(2026, 8, 21), date(2026, 8, 23),  # 22nd forgotten
                date(2026, 9, 18), date(2026, 9, 19), date(2026, 9, 20)]
        self.assertEqual(tracking.periods_from_days(days), [
            (date(2026, 8, 20), date(2026, 8, 23)),
            (date(2026, 9, 18), date(2026, 9, 20)),
        ])

    def test_cycle_summary_predicts_next_start(self):
        periods = [(date(2026, 8, 20), date(2026, 8, 24)), (date(2026, 9, 18), date(2026, 9, 22))]
        summary = tracking.cycle_summary(periods, TODAY)
        self.assertEqual(summary["average_cycle"], 29)
        self.assertEqual(summary["next_start"], date(2026, 10, 17))
        self.assertEqual(summary["days_until"], 1)

    def test_one_period_is_not_enough_to_predict(self):
        self.assertIsNone(tracking.cycle_summary([(TODAY, TODAY)], TODAY)["next_start"])


class MedicationScheduleTests(unittest.TestCase):
    def med(self, frequency, start=date(2026, 10, 1), doses=2):
        return {"frequency": frequency, "start_date": start, "doses_per_day": doses}

    def test_frequencies(self):
        self.assertTrue(tracking.medication_due(self.med("daily"), TODAY))
        self.assertFalse(tracking.medication_due(self.med("every_other_day"), TODAY))     # 15 days after start
        self.assertTrue(tracking.medication_due(self.med("every_other_day"), TODAY - timedelta(days=1)))
        self.assertTrue(tracking.medication_due(self.med("weekly", start=date(2026, 10, 9)), TODAY))  # both Fridays
        self.assertFalse(tracking.medication_due(self.med("weekly", start=date(2026, 10, 8)), TODAY))
        self.assertFalse(tracking.medication_due(self.med("daily", start=date(2026, 11, 1)), TODAY))  # not started

    def test_dose_count_is_clamped_to_eight(self):
        self.assertEqual(tracking.dose_count({"doses_per_day": "12"}), 8)
        self.assertEqual(tracking.dose_count({"doses_per_day": 0}), 1)
        self.assertEqual(tracking.dose_count({"doses_per_day": "3"}), 3)


class AppMinutesTests(unittest.TestCase):
    def test_sums_overlap_with_the_day_and_caps_open_sessions(self):
        start, end = datetime(2026, 10, 16, 4), datetime(2026, 10, 17, 4)
        sessions = [
            {"opened_at": datetime(2026, 10, 16, 3, 50), "closed_at": datetime(2026, 10, 16, 4, 10)},  # 10 min inside
            {"opened_at": datetime(2026, 10, 16, 12, 0), "closed_at": datetime(2026, 10, 16, 12, 25)},  # 25
            {"opened_at": datetime(2026, 10, 16, 20, 0), "closed_at": None},  # still open: up to "now"
        ]
        self.assertEqual(tracking.session_minutes(sessions, start, end, datetime(2026, 10, 16, 20, 5)), 40)

    def test_local_day_bounds_follow_the_timezone(self):
        start, end = tracking.local_day_bounds_utc(TODAY, "Asia/Manila")
        self.assertEqual(start, datetime(2026, 10, 15, 16))
        self.assertEqual(end, datetime(2026, 10, 16, 16))


class PhoneTrackingEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("blueprints.admin.personal.tracking.token_matches", return_value=False)
    def test_wrong_token_looks_like_a_missing_page(self, _):
        resp = self.client.post("/gc-admin/track/sleep", json={"hours": 7}, headers={"Authorization": "Bearer nope"})
        self.assertEqual(resp.status_code, 404)

    @patch("blueprints.admin.personal.local_today", return_value=TODAY)
    @patch("blueprints.admin.personal.tracking.record_sleep")
    @patch("blueprints.admin.personal.tracking.token_matches", return_value=True)
    def test_sleep_hours_are_stored_as_minutes_without_csrf(self, _, mock_record, __):
        resp = self.client.post("/gc-admin/track/sleep", json={"hours": 7.25}, headers={"Authorization": "Bearer t"})
        self.assertEqual(resp.status_code, 200)
        mock_record.assert_called_once_with(TODAY, 435)
        bad = self.client.post("/gc-admin/track/sleep", json={"hours": 30}, headers={"Authorization": "Bearer t"})
        self.assertEqual(bad.status_code, 400)

    @patch("blueprints.admin.personal.tracking.record_app_event")
    @patch("blueprints.admin.personal.tracking.token_matches", return_value=True)
    def test_app_events(self, _, mock_record):
        resp = self.client.post("/gc-admin/track/app", json={"event": "Opened"}, headers={"Authorization": "Bearer t"})
        self.assertEqual(resp.status_code, 200)
        mock_record.assert_called_once_with("Instagram", "opened")
        bad = self.client.post("/gc-admin/track/app", json={"event": "scrolled"}, headers={"Authorization": "Bearer t"})
        self.assertEqual(bad.status_code, 400)


class PersonalDashboardTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")

    @patch("blueprints.admin.personal.checkin_streak", return_value=3)
    @patch("blueprints.admin.personal.local_tz_name", return_value="America/New_York")
    @patch("blueprints.admin.personal.local_today", return_value=TODAY)
    @patch("blueprints.admin.personal.tracking")
    @patch("blueprints.admin.personal.query")
    def test_dashboard_renders(self, mock_query, mock_tracking, *_):
        def fake_query(sql, *args):
            if "food_breakfast, food_lunch" in sql:
                return [{"checkin_date": TODAY, "food_breakfast": "Oatmeal", "food_lunch": None, "food_dinner": "Sinigang", "food_snacks": None}]
            if "FROM app_ideas" in sql:
                return [{"id": 5, "idea": "Prayer streak widget", "details": "Android home screen"}]
            if "period_day = 1" in sql:
                return [{"checkin_date": date(2026, 9, 18)}, {"checkin_date": date(2026, 9, 19)}]
            if "AS text" in sql:
                if "bible_passage" in sql:
                    return [{"checkin_date": TODAY, "text": "Psalm 23"}]
                return [{"checkin_date": TODAY, "text": "Jinja macros"}] if "learnings" in sql else []
            if "mood_reason" in sql and "LIMIT 14" in sql:
                return [{"checkin_date": TODAY, "mood": 4, "mood_reason": "Good sleep"}]
            return [{"checkin_date": TODAY, "mood": 4, "energy": 3, "morning_prayer": 1, "night_prayer": 1, "water_glasses": 6}]

        mock_query.side_effect = fake_query
        mock_tracking.sleep_by_day.return_value = {TODAY: 420}
        mock_tracking.app_minutes_by_day.return_value = {TODAY: 30}
        mock_tracking.active_medications.return_value = []
        mock_tracking.doses_taken.return_value = {}
        mock_tracking.periods_from_days.side_effect = tracking.periods_from_days
        mock_tracking.cycle_summary.side_effect = tracking.cycle_summary
        mock_tracking.ingest_token.return_value = "secret-token"
        mock_tracking.tracking_status.return_value = {"last_sleep": None, "last_app": None}
        mock_tracking.TRACKED_APP = "Instagram"

        resp = self.client.get("/gc-admin/me")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        for text in ("My dashboard", "Good sleep", "Psalm 23", "What I learned", "Jinja macros",
                     "Prayer streak widget", "Android home screen", "/gc-admin/app_ideas/5/edit", "Sep 18 – Sep 19", "Period cycle",
                     "/gc-admin/track/sleep", "7h 00m", "6.0/8", "Glasses of water", "Food log", "Oatmeal", "Sinigang"):
            self.assertIn(text, body)
        self.assertIn('data-token="secret-token"', body)
        self.assertNotIn(">secret-token<", body)  # masked until "Show"
        self.assertIn('name="robots" content="noindex, nofollow"', body)

    def test_dashboard_requires_login(self):
        resp = self.app.test_client().get("/gc-admin/me")
        self.assertEqual(resp.status_code, 302)


class MedicinesEditorTests(unittest.TestCase):
    """doses_per_day is an INT column behind a select field — the list and
    edit pages must handle a number, not just strings (this 500'd once)."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))

    ROW = {"id": 1, "name": "Vitamin D", "doses_per_day": 3, "frequency": "every_other_day",
           "start_date": date(2026, 10, 1), "is_active": 1, "notes": None, "sort_order": 0}

    @patch("blueprints.admin.simple_crud.query")
    def test_list_page_renders_int_select_values(self, mock_query):
        mock_query.return_value = [self.ROW]
        resp = self.client.get("/gc-admin/medications")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn("Vitamin D", body)
        self.assertIn("every other day", body)

    @patch("blueprints.admin.simple_crud.query_one")
    def test_edit_form_preselects_the_saved_dose_count(self, mock_query_one):
        mock_query_one.return_value = self.ROW
        body = self.client.get("/gc-admin/medications/1/edit").get_data(as_text=True)
        self.assertIn('<option value="3" selected>', body)
        self.assertNotIn('<option value="1" selected>', body)


if __name__ == "__main__":
    unittest.main()

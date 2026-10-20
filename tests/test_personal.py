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


class SleepModeTests(unittest.TestCase):
    def test_minutes_between_start_and_end(self):
        start = datetime(2026, 10, 18, 15, 0)  # UTC
        self.assertEqual(tracking.sleep_minutes_between(start, start + timedelta(hours=7, minutes=20)), 440)

    def test_naps_and_missed_ends_are_ignored(self):
        start = datetime(2026, 10, 18, 15, 0)
        self.assertIsNone(tracking.sleep_minutes_between(start, start + timedelta(minutes=40)))
        self.assertIsNone(tracking.sleep_minutes_between(start, start + timedelta(hours=20)))
        self.assertIsNone(tracking.sleep_minutes_between(None, start))


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

    @patch("blueprints.admin.personal.local_today", return_value=TODAY)
    @patch("blueprints.admin.personal.tracking.record_sleep_event", return_value=440)
    @patch("blueprints.admin.personal.tracking.token_matches", return_value=True)
    def test_sleep_mode_start_and_end_events(self, _, mock_event, __):
        self.client.post("/gc-admin/track/sleep", json={"event": "start"}, headers={"Authorization": "Bearer t"})
        resp = self.client.post("/gc-admin/track/sleep", json={"event": "END"}, headers={"Authorization": "Bearer t"})
        self.assertEqual(resp.get_json(), {"ok": True, "minutes": 440})
        self.assertEqual([c.args for c in mock_event.call_args_list], [("start", TODAY), ("end", TODAY)])

    @patch("blueprints.admin.personal.tracking.record_app_event")
    @patch("blueprints.admin.personal.tracking.token_matches", return_value=True)
    def test_app_events(self, _, mock_record):
        resp = self.client.post("/gc-admin/track/app", json={"event": "Opened"}, headers={"Authorization": "Bearer t"})
        self.assertEqual(resp.status_code, 200)
        mock_record.assert_called_once_with("Instagram", "opened")
        bad = self.client.post("/gc-admin/track/app", json={"event": "scrolled"}, headers={"Authorization": "Bearer t"})
        self.assertEqual(bad.status_code, 400)


class PeriodDaysTests(unittest.TestCase):
    def test_week_runs_sunday_to_saturday(self):
        from blueprints.admin.personal import period_days
        days, prev, nxt = period_days("week", date(2026, 10, 19))  # a Monday
        self.assertEqual((days[0], days[-1]), (date(2026, 10, 18), date(2026, 10, 24)))
        self.assertEqual(days[0].strftime("%a"), "Sun")
        self.assertEqual((prev, nxt), (date(2026, 10, 11), date(2026, 10, 25)))

    def test_month(self):
        from blueprints.admin.personal import period_days
        days, prev, nxt = period_days("month", date(2026, 2, 14))
        self.assertEqual((days[0], days[-1], len(days)), (date(2026, 2, 1), date(2026, 2, 28), 28))
        self.assertEqual((prev, nxt), (date(2026, 1, 1), date(2026, 3, 1)))


class PersonalDashboardTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")

    ENTRY = {"checkin_date": TODAY, "mood": 4, "energy": 5, "morning_prayer": 0, "night_prayer": 0,
             "morning_prayer_note": "Guide me", "night_prayer_note": None, "bible_passage": "Psalm 23",
             "devotion_thoughts": None, "water_glasses": 6, "exercised": 1, "period_day": 0,
             "food_breakfast": "Oatmeal", "food_lunch": None, "food_dinner": "Sinigang", "food_snacks": None,
             "reading": None, "learnings": "Jinja", "win": None}

    def render(self, path):
        def fake_query(sql, *args):
            if "period_day = 1" in sql:
                return [{"checkin_date": date(2026, 9, 18)}, {"checkin_date": date(2026, 9, 19)}]
            if "morning_prayer = 1 AND night_prayer = 1" in sql:
                return []
            return [self.ENTRY]

        with patch("blueprints.admin.personal.checkin_streak", return_value=3), \
             patch("blueprints.admin.personal.local_tz_name", return_value="UTC"), \
             patch("blueprints.admin.personal.local_today", return_value=TODAY), \
             patch("blueprints.admin.personal.query", side_effect=fake_query), \
             patch("blueprints.admin.personal.tracking") as t:
            t.sleep_by_day.return_value = {TODAY: 420}
            t.app_minutes_by_day.return_value = {TODAY: 30}
            t.active_medications.return_value = [{"id": 1, "name": "Vitamin D", "frequency": "daily", "doses_per_day": 2, "start_date": None}]
            t.doses_taken.return_value = {(1, TODAY): {1}}
            t.medication_due.side_effect = tracking.medication_due
            t.dose_count.side_effect = tracking.dose_count
            t.periods_from_days.side_effect = tracking.periods_from_days
            t.cycle_summary.side_effect = tracking.cycle_summary
            t.ingest_token.return_value = "secret-token"
            t.tracking_status.return_value = {"last_sleep": None, "last_app": None}
            t.TRACKED_APP = "Instagram"
            resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        return resp.get_data(as_text=True)

    def test_weekly_grid_starts_sunday_and_shows_only_emojis_and_checks(self):
        body = self.render("/gc-admin/me")  # TODAY is Friday Oct 16
        self.assertIn("Oct 11 – Oct 17", body)                   # Sunday..Saturday
        first_day = body.split('class="habit-dow">')[1][:1]
        self.assertEqual(first_day, "S")
        self.assertIn('href="/gc-admin/today?date=2026-10-11"', body)
        self.assertIn('habit-cell--emoji is-today">🙂', body)   # mood 4
        self.assertIn('habit-cell--emoji is-today">⚡', body)    # energy 5
        self.assertIn('habit-cell--part is-today">✓', body)      # 1 of 2 doses: amber check, no numbers
        self.assertNotIn("%", body.split('class="habit-grid')[1].split("</table>")[0])
        self.assertIn('habit-cell--water-6 is-today">6', body)
        # Sentences are gone: only the grid, graphs, cycle chips and phone setup.
        content = body.split('<main class="admin-main">')[1]  # the sidebar still links App ideas
        for gone in ("Why I felt that way", "Food log", "Oatmeal", "Psalm 23", "App ideas", "Guide me", "Jinja"):
            self.assertNotIn(gone, content)
        self.assertIn('data-token="secret-token"', body)
        self.assertNotIn(">secret-token<", body)
        self.assertIn('name="robots" content="noindex, nofollow"', body)

    def test_prayer_rows_check_when_a_prayer_was_written(self):
        body = self.render("/gc-admin/me")
        grid = body.split('class="habit-grid')[1]
        morning = grid.split("Morning prayer</span></th>")[1].split("</tr>")[0]
        evening = grid.split("Evening prayer</span></th>")[1].split("</tr>")[0]
        self.assertIn('habit-cell--done is-today">✓', morning)   # wrote a morning prayer
        self.assertIn('habit-cell--empty is-today">', evening)   # no evening prayer written

    def test_monthly_tab_and_period_navigation(self):
        body = self.render("/gc-admin/me?view=month&d=2026-10-05")
        self.assertIn("October 2026", body)
        self.assertEqual(body.count('class="habit-dom">'), 31)
        self.assertIn('href="/gc-admin/me?view=month&amp;d=2026-09-01"', body)  # previous month
        self.assertIn("checkin-daynav-step is-disabled", body)                  # no future months

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

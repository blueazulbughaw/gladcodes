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
             "reading": None, "learnings": "Jinja", "win": None, "grateful": None}
    BIBLE = {"covered": 112, "total": 1189, "percent": 9.4, "books_started": 9, "books_finished": 2, "by_book": {}}

    def render(self, path):
        def fake_query(sql, *args):
            if "period_day = 1" in sql:
                return [{"checkin_date": date(2026, 9, 18)}, {"checkin_date": date(2026, 9, 19)}]
            if "morning_prayer = 1 AND night_prayer = 1" in sql:
                return []
            if "FROM app_ideas" in sql:
                return [{"n": 4}]
            return [self.ENTRY]

        with patch("blueprints.admin.personal.checkin_streak", return_value=3), \
             patch("blueprints.admin.personal.local_tz_name", return_value="UTC"), \
             patch("blueprints.admin.personal.local_today", return_value=TODAY), \
             patch("blueprints.admin.personal.query", side_effect=fake_query), \
             patch("blueprints.admin.personal.configured_username", return_value="glad"), \
             patch("blueprints.admin.personal.get_weekly_activity", return_value={"labels": ["Oct 12"], "data": [2]}), \
             patch("blueprints.admin.personal.devotion.bible_progress", return_value=self.BIBLE), \
             patch("blueprints.admin.personal.tracking") as t:
            t.sleep_by_day.return_value = {TODAY: 420}
            t.app_minutes_by_day.return_value = {TODAY: 30}
            t.active_medications.return_value = [{"id": 1, "name": "Vitamin D", "frequency": "daily", "doses_per_day": 2, "start_date": None}]
            t.doses_taken.return_value = {(1, TODAY): {1}}
            t.medication_due.side_effect = tracking.medication_due
            t.dose_count.side_effect = tracking.dose_count
            t.periods_from_days.side_effect = tracking.periods_from_days
            t.cycle_summary.side_effect = tracking.cycle_summary
            t.TRACKED_APP = "Instagram"
            resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        return resp.get_data(as_text=True)

    @staticmethod
    def section(body, key):
        return body.split(f'data-section="{key}"')[1].split("</details>")[0]

    def test_sections_in_order_and_collapsible(self):
        body = self.render("/gc-admin/me")
        keys = ["today", "prayer", "mind", "health", "growth", "app"]
        positions = [body.index(f'data-section="{k}"') for k in keys]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('<details class="card dash-section" data-section="prayer" open>', body)
        self.assertIn('<details class="card dash-section" data-section="app">', body)  # closed by default
        self.assertIn("gc-dashboard-sections", body)  # remembers open/closed per device

    def test_today_strip_links_to_each_input_page(self):
        strip = self.section(self.render("/gc-admin/me"), "today")
        self.assertIn('today-item--done" href="/gc-admin/prayer" title="Morning prayer"', strip)
        self.assertIn('today-item--empty" href="/gc-admin/prayer" title="Evening prayer"', strip)
        self.assertIn('href="/gc-admin/emotions" title="Mood"', strip)
        self.assertIn("🙂", strip)
        self.assertIn('today-item--part" href="/gc-admin/medicine" title="Medicines"', strip)
        self.assertIn(">1/2<", strip)   # doses
        self.assertIn(">6/8<", strip)   # water
        self.assertIn(">2/4<", strip)   # meals
        self.assertIn('href="/gc-admin/learnings"', strip)

    def test_weekly_grids_start_sunday_and_show_only_emojis_and_checks(self):
        body = self.render("/gc-admin/me")  # TODAY is Friday Oct 16
        self.assertIn("Oct 11 – Oct 17", body)                   # Sunday..Saturday
        first_day = body.split('class="habit-dow">')[1][:1]
        self.assertEqual(first_day, "S")
        self.assertIn('href="/gc-admin/prayer?date=2026-10-11"', self.section(body, "prayer"))
        self.assertIn('href="/gc-admin/emotions?date=2026-10-11"', self.section(body, "mind"))
        self.assertIn('href="/gc-admin/body?date=2026-10-11"', self.section(body, "health"))
        self.assertIn('href="/gc-admin/learnings?date=2026-10-11"', self.section(body, "growth"))
        mind, health = self.section(body, "mind"), self.section(body, "health")
        self.assertIn('habit-cell--emoji is-today">🙂', mind)   # mood 4
        self.assertIn('habit-cell--emoji is-today">⚡', mind)    # energy 5
        self.assertIn('habit-cell--part is-today">✓', health)   # 1 of 2 doses: amber check, no numbers
        self.assertIn('habit-cell--water-6 is-today">6', health)
        self.assertIn('💻 2</span><span class="overview-label">GitHub pushes this week', self.section(body, "growth"))
        # No sentences: the words live on the input pages.
        content = body.split('<main class="admin-main">')[1]
        for gone in ("Why I felt that way", "Food log", "Oatmeal", "Psalm 23", "Guide me", "Jinja"):
            self.assertNotIn(gone, content)
        self.assertIn('name="robots" content="noindex, nofollow"', body)

    def test_bible_progress_in_prayer_section(self):
        prayer = self.section(self.render("/gc-admin/me"), "prayer")
        self.assertIn("📖 112 <small>/ 1,189</small>", prayer)
        self.assertIn('aria-valuenow="112"', prayer)
        self.assertIn("width: 9.4%", prayer)

    def test_prayer_rows_check_when_a_prayer_was_written(self):
        grid = self.section(self.render("/gc-admin/me"), "prayer")
        morning = grid.split("Morning prayer</span></th>")[1].split("</tr>")[0]
        evening = grid.split("Evening prayer</span></th>")[1].split("</tr>")[0]
        self.assertIn('habit-cell--done is-today">✓', morning)   # wrote a morning prayer
        self.assertIn('habit-cell--empty is-today">', evening)   # no evening prayer written

    def test_monthly_tab_and_period_navigation(self):
        body = self.render("/gc-admin/me?view=month&d=2026-10-05")
        self.assertIn("October 2026", body)
        self.assertEqual(self.section(body, "prayer").count('class="habit-dom">'), 31)
        self.assertIn('href="/gc-admin/me?view=month&amp;d=2026-09-01"', body)  # previous month
        self.assertIn("checkin-daynav-step is-disabled", body)                  # no future months

    def test_dashboard_requires_login(self):
        resp = self.app.test_client().get("/gc-admin/me")
        self.assertEqual(resp.status_code, 302)

    def test_devotion_is_done_only_with_my_thoughts(self):
        from blueprints.admin.personal import devotion_state
        base = {"bible_passage": None, "devotion_thoughts": None, "devotion_markdown": None}
        self.assertEqual(devotion_state(None), "empty")
        self.assertEqual(devotion_state(base), "empty")
        self.assertEqual(devotion_state(dict(base, bible_passage="Psalm 37")), "part")
        self.assertEqual(devotion_state(dict(base, devotion_markdown="# Waiting on God")), "part")
        self.assertEqual(devotion_state(dict(base, bible_passage="Psalm 37", devotion_thoughts="  ")), "part")
        self.assertEqual(devotion_state(dict(base, bible_passage="Psalm 37", devotion_thoughts="He is near")), "done")
        # ENTRY has a passage but no thoughts: amber on the strip and in the grid.
        body = self.render("/gc-admin/me")
        self.assertIn('today-item--part" href="/gc-admin/prayer" title="Devotion"', self.section(body, "today"))
        devotion_row = self.section(body, "prayer").split("Devotion</span></th>")[1].split("</tr>")[0]
        self.assertIn('habit-cell--part is-today">✓', devotion_row)

    def test_switched_off_sections_are_not_shown(self):
        with patch("blueprints.admin.personal.hidden_sections", return_value={"mind", "app"}):
            body = self.render("/gc-admin/me")
        for key in ("today", "prayer", "health", "growth"):
            self.assertIn(f'data-section="{key}"', body)
        self.assertNotIn('data-section="mind"', body)
        self.assertNotIn('data-section="app"', body)
        self.assertNotIn("installBtn", body)  # its script is skipped too
        self.assertIn('href="/gc-admin/me/settings"', body)

    def test_settings_page_saves_which_sections_show(self):
        with patch("blueprints.admin.personal.hidden_sections", return_value={"growth"}):
            page = self.client.get("/gc-admin/me/settings").get_data(as_text=True)
        self.assertIn('name="show" value="prayer" role="switch" checked', page)
        self.assertIn('name="show" value="growth" role="switch" >', page)
        with patch("blueprints.admin.personal.execute") as mock_execute:
            resp = self.client.post("/gc-admin/me/settings", data={
                "csrf_token": "test-csrf", "show": ["today", "prayer", "health", "bogus"]})
        self.assertTrue(resp.headers["Location"].endswith("/gc-admin/me"))
        self.assertEqual(mock_execute.call_args[0][1], ("mind,growth,app",))
        with patch("blueprints.admin.personal.execute") as mock_execute:
            self.client.post("/gc-admin/me/settings", data={"show": ["today"]})  # no CSRF token
        self.assertFalse(mock_execute.called)

    def test_hidden_sections_ignores_unknown_keys(self):
        from blueprints.admin import personal
        with patch("blueprints.admin.personal.query_one", return_value={"dashboard_hidden": "mind,bogus,app"}):
            self.assertEqual(personal.hidden_sections(), {"mind", "app"})
        with patch("blueprints.admin.personal.query_one", return_value={"dashboard_hidden": None}):
            self.assertEqual(personal.hidden_sections(), set())

    def test_phone_tracking_page_hides_the_key(self):
        with patch("blueprints.admin.personal.tracking") as t:
            t.ingest_token.return_value = "secret-token"
            t.tracking_status.return_value = {"last_sleep": None, "last_app": None}
            t.TRACKED_APP = "Instagram"
            body = self.client.get("/gc-admin/connectors/phone").get_data(as_text=True)
        self.assertIn('data-token="secret-token"', body)
        self.assertNotIn(">secret-token<", body)
        self.assertIn("/gc-admin/track/sleep", body)


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

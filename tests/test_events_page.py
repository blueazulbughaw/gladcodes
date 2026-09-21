import unittest
from datetime import datetime
from unittest.mock import patch

from app import create_app

# blueprints.public.routes.query is also called by the module's own
# inject_site_globals context processor (for site_settings) on every
# request, so a blanket mock return value would clobber that call too —
# dispatch on the SQL text instead of stubbing a single return value.
SETTINGS_ROWS = []


def _query_side_effect(rows_for_route):
    def side_effect(sql, *args, **kwargs):
        if "site_settings" in sql:
            return SETTINGS_ROWS
        return rows_for_route

    return side_effect


class EventsPageTests(unittest.TestCase):
    """/events lists everything I'm attending, volunteering at, organizing,
    or speaking at — the old standalone /speaking page was folded in via
    the attending_as dropdown."""

    def setUp(self):
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    @patch("blueprints.public.routes.query")
    def test_events_page_renders(self, mock_query):
        mock_query.side_effect = _query_side_effect(
            [
                {
                    "id": 1,
                    "event_name": "PyCon Philippines",
                    "attending_as": "Attendee",
                    "datetime_from": datetime(2026, 5, 14),
                    "datetime_to": datetime(2026, 5, 16),
                    "status": "confirmed",
                    "location": "Manila, Philippines",
                    "link": None,
                    "description": "Scouting talks on developer tooling.",
                    "sort_order": 1,
                },
                {
                    "id": 2,
                    "event_name": "Undated meetup",
                    "attending_as": "Attendee",
                    "datetime_from": None,
                    "datetime_to": None,
                    "status": "tentative",
                    "location": None,
                    "link": None,
                    "description": None,
                    "sort_order": 2,
                },
            ]
        )

        response = self.client.get("/events")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Events", response.data)
        self.assertIn(b"PyCon Philippines", response.data)
        self.assertIn(b"Confirmed", response.data)
        # Undated row still renders (it's on the caller/DB to order it last
        # via "datetime_from IS NULL, datetime_from ASC" — the route just
        # displays whatever order the query returns).
        self.assertIn(b"Undated meetup", response.data)

    @patch("blueprints.public.routes.query")
    def test_events_query_orders_undated_rows_last(self, mock_query):
        mock_query.side_effect = _query_side_effect([])

        self.client.get("/events")

        events_sql = next(
            call.args[0] for call in mock_query.call_args_list if "attending_events" in call.args[0]
        )
        self.assertIn("datetime_from IS NULL", events_sql)
        self.assertIn("datetime_from ASC", events_sql)

    def test_speaking_route_removed(self):
        response = self.client.get("/speaking")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()

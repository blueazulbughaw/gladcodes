import unittest
from datetime import datetime
from unittest.mock import patch

from app import create_app

ROWS = {
    "stat_counters": [{"label": "Projects shipped", "value": 12, "suffix": ""}],
    "projects": [{"title": "GladCodes", "description": "This site.", "icon": "rocket", "status": "in_progress", "progress_pct": 80, "url": None}],
    "journal_posts": [{"title": "Why I build in public", "slug": "why", "excerpt": "Notes.", "published_at": datetime(2026, 10, 2)}],
    "timeline_milestones": [{"month_label": "Oct 2026", "title": "Daily check-in app", "description": None, "is_done": 1}],
    "learning_progress": [{"skill": "GSAP", "progress_pct": 55}],
    "toolbox_items": [{"name": "Flask", "icon": "flask-conical", "url": None}],
    "community_links": [{"org_name": "PyCon Philippines", "icon": "users", "url": "https://pycon.ph"}],
}
NOW = {"location": "Manila", "building": "Check-in app", "drinking": "Latte", "reading": "DDIA",
       "goal_this_week": "Ship home", "updated_at": datetime(2026, 10, 16)}


def fake_query(sql, *args):
    for table, rows in ROWS.items():
        if f"FROM {table}" in sql:
            return rows
    return []


class HomePageTests(unittest.TestCase):
    """The AIDA landing page: every chapter renders from DB data, GitHub is
    optional, motion is a progressive enhancement, and nothing links /gc-admin."""

    def setUp(self):
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def get_home(self, github=None):
        with patch("blueprints.public.routes.query", side_effect=fake_query), \
             patch("blueprints.public.routes.query_one", return_value=NOW), \
             patch("blueprints.public.routes.get_chart_series", return_value={"labels": ["W1"], "data": [5]}), \
             patch("blueprints.public.routes.configured_username", return_value=None), \
             patch("blueprints.public.routes.get_profile_summary", return_value=github):
            resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        return resp.get_data(as_text=True)

    def test_all_chapters_render(self):
        body = self.get_home()
        for text in ("I don't know exactly what I'm doing.", "Right now", "Check-in app",
                     "The numbers behind the building", "Currently learning", "The timeline so far",
                     "data-scrub-words", "What I'm building", "accordion-slice", "Notes from the road",
                     "marquee-track", "PyCon Philippines", "hire the person behind it", "newsletter-form",
                     "home-motion.js"):
            self.assertIn(text, body)

    def test_github_card_only_when_github_loads(self):
        self.assertNotIn("Fresh on GitHub", self.get_home())
        github = {"profile": {"html_url": "https://github.com/x"},
                  "repos": [{"name": "gladcodes", "html_url": "#", "description": "Site", "language": "Python", "pushed_at": None}]}
        body = self.get_home(github)
        self.assertIn("Fresh on GitHub", body)
        self.assertIn("bento--with-github", body)

    def test_marquee_duplicate_is_hidden_from_screen_readers(self):
        body = self.get_home()
        # Two marquees (toolbox, community), each = 1 visible track + 1 aria-hidden copy.
        self.assertEqual(body.count('class="marquee-track"'), 4)
        self.assertEqual(body.count('class="marquee-track" aria-hidden="true"'), 2)

    def test_never_links_to_admin(self):
        self.assertNotIn("gc-admin", self.get_home())


if __name__ == "__main__":
    unittest.main()

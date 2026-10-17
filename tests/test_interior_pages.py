import unittest
from datetime import datetime
from unittest.mock import patch

from app import create_app

POSTS = [
    {"title": "Newest post", "slug": "new", "excerpt": "Fresh.", "published_at": datetime(2026, 10, 9), "tags": ""},
    {"title": "Older post", "slug": "old", "excerpt": "Less fresh.", "published_at": datetime(2026, 9, 9), "tags": ""},
]
PROJECTS = [{"title": f"Project {i}", "description": "d", "icon": "rocket", "status": "launched", "progress_pct": 50, "url": None}
            for i in range(6)]
ROWS = {
    "journal_posts": POSTS,
    "projects": PROJECTS,
    "stat_counters": [{"label": "Projects shipped", "value": 12, "suffix": ""}],
}


def fake_query(sql, *args):
    for table, rows in ROWS.items():
        if f"FROM {table}" in sql:
            return rows
    return []


class InteriorPagesTests(unittest.TestCase):
    """Shared interior-page treatment: closing CTA band (except pages with
    their own ending), no eyebrow meta-labels, page-specific layouts."""

    def setUp(self):
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def get(self, path):
        with patch("blueprints.public.routes.query", side_effect=fake_query), \
             patch("blueprints.public.routes.query_one", return_value=None), \
             patch("blueprints.public.routes.get_chart_series", return_value={"labels": [], "data": []}), \
             patch("blueprints.public.routes.get_weekly_activity", return_value=None), \
             patch("blueprints.public.routes.configured_username", return_value=None):
            resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200, path)
        return resp.get_data(as_text=True)

    def test_closing_cta_on_interior_pages_only(self):
        for path in ("/projects", "/journal", "/dashboard", "/about", "/events", "/resources"):
            self.assertIn('class="closing-cta"', self.get(path), path)
        for path in ("/contact", "/resume"):  # these end with their own call to action
            self.assertNotIn('class="closing-cta"', self.get(path), path)

    def test_no_eyebrow_labels_or_admin_links(self):
        for path in ("/projects", "/journal", "/dashboard", "/about", "/events", "/resources", "/contact", "/resume"):
            body = self.get(path)
            self.assertNotIn('class="eyebrow', body, path)
            self.assertNotIn("gc-admin", body, path)

    def test_projects_render_as_accordion_rows_of_four(self):
        body = self.get("/projects")
        self.assertEqual(body.count('class="accordion"'), 2)  # 6 projects -> 4 + 2
        self.assertEqual(body.count('class="accordion-slice"'), 6)

    def test_journal_features_newest_post(self):
        body = self.get("/journal")
        self.assertIn('class="journal-feature" href="/journal/new"', body)
        self.assertLess(body.index("Newest post"), body.index("Older post"))

    def test_dashboard_counter_hook_sits_on_the_number(self):
        # animations.js only counts up elements that are both .reveal and
        # carry data-count-to; on the tile wrapper it silently showed "0".
        body = self.get("/dashboard")
        self.assertIn('class="stat-value reveal" data-count-to="12"', body)


if __name__ == "__main__":
    unittest.main()

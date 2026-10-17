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


class PageClient(unittest.TestCase):
    """Renders public pages with the DB mocked (base class, no tests)."""

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


class InteriorPagesTests(PageClient):
    """Shared interior-page treatment: closing CTA band (except pages with
    their own ending), no eyebrow meta-labels, page-specific layouts."""

    def test_closing_cta_on_interior_pages_only(self):
        shared = 'id="closingCtaTitle"'  # the shared band's heading
        for path in ("/projects", "/journal", "/dashboard", "/about", "/events", "/resources"):
            self.assertIn(shared, self.get(path), path)
        self.assertNotIn('class="closing-cta"', self.get("/contact"))  # the page itself is the CTA
        resume = self.get("/resume")  # same navy band style, its own download content
        self.assertNotIn(shared, resume)
        self.assertIn('id="resumeCtaTitle"', resume)

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


class StoryPagesTests(PageClient):
    """About + Resume follow the same design language."""

    TIMELINE = [
        {"period_label": "2005", "title": "BS Computer Science", "company": "Uni", "summary": "s", "entry_type": "education", "resume_bullets": "Honors"},
        {"period_label": "2009", "title": "Software Engineer", "company": "Tokyo", "summary": "s", "entry_type": "full_time", "resume_bullets": "Built tools\nCut time 70%"},
        {"period_label": "2016", "title": "Side venture", "company": "Self", "summary": "s", "entry_type": "side_venture", "resume_bullets": ""},
        {"period_label": "2023", "title": "Founder", "company": "GladCodes", "summary": "s", "entry_type": "side_venture", "resume_bullets": ""},
    ]

    def setUp(self):
        super().setUp()
        ROWS["resume_timeline"] = self.TIMELINE

    def tearDown(self):
        ROWS.pop("resume_timeline", None)

    def test_about_numbers_are_counted_from_the_timeline(self):
        body = self.get("/about")
        self.assertIn('<span class="story-stat-value">4</span><span class="story-stat-label">stops', body)
        self.assertIn('<span class="story-stat-value">2</span><span class="story-stat-label">side ventures', body)
        self.assertIn("BS Computer Science", body.split("Where it started")[1].split("Where I am now")[0])
        self.assertIn("Founder", body.split("Where I am now")[1])

    def test_resume_title_keeps_mba_mis_together_and_has_pinned_experience(self):
        body = self.get("/resume")
        self.assertIn("MBA&#8209;MIS", body)
        self.assertIn('class="resume-split-pin"', body)
        self.assertEqual(body.count('class="resume-layer resume-layer--'), 4)
        self.assertIn("<li>Cut time 70%</li>", body)


class ConnectPageTests(PageClient):
    """/lets-connect: link-in-bio cards with icons picked from each URL."""

    LINKS = [{"label": "GitHub", "url": "https://github.com/blueazulbughaw"},
             {"label": "Resume", "url": "/resume"},
             {"label": "Newsletter", "url": "/#newsletter"}]

    def setUp(self):
        super().setUp()
        ROWS["page_links"] = self.LINKS

    def tearDown(self):
        ROWS.pop("page_links", None)

    def test_links_render_as_cards_with_icons_and_hints(self):
        body = self.get("/lets-connect")
        self.assertEqual(body.count('class="connect-link reveal"'), 3)
        self.assertIn("github.com/blueazulbughaw</span>", body)
        self.assertIn("glad.codes/resume</span>", body)
        self.assertIn('data-lucide="file-text"', body)   # /resume
        self.assertIn('data-lucide="mail"', body)        # newsletter
        self.assertIn('href="https://github.com/blueazulbughaw" target="_blank"', body)
        self.assertIn('href="/resume" >', body)           # internal: same tab

    def test_no_shared_closing_cta_or_admin_links(self):
        body = self.get("/lets-connect")
        self.assertNotIn('class="closing-cta"', body)
        self.assertNotIn("gc-admin", body)


class BrandTests(PageClient):
    def test_logo_and_favicon_on_public_pages(self):
        for path in ("/projects", "/about", "/contact", "/lets-connect"):
            body = self.get(path)
            self.assertIn('class="nav-logo"', body, path)
            self.assertEqual(body.count('class="logo-mark '), 2, path)   # nav + footer
            self.assertIn('img/brand/favicon.svg', body, path)
            self.assertIn('aria-label="glad.codes home"', body, path)
            self.assertNotIn("&lt;/&gt; glad.codes", body, path)       # old text logo gone

    def test_admin_login_stays_unbranded(self):
        body = self.client.get("/gc-admin/login").get_data(as_text=True)
        self.assertNotIn("logo-mark", body)
        self.assertNotIn("favicon", body)


if __name__ == "__main__":
    unittest.main()

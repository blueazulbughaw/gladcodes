import unittest

from flask import request

from app import create_app
from blueprints.admin.routes import back_url


class BackButtonTests(unittest.TestCase):
    """Every admin page except the two "homes" gets a Back button pointing
    at its parent page (not browser history)."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True

    def back_for(self, path):
        with self.app.test_request_context(path):
            # test_request_context doesn't run routing; match it ourselves.
            adapter = self.app.url_map.bind("localhost")
            request.url_rule, request.view_args = adapter.match(path, method="GET", return_rule=True)
            return back_url()

    def test_homes_have_no_back_button(self):
        self.assertIsNone(self.back_for("/gc-admin/today"))
        self.assertIsNone(self.back_for("/gc-admin/"))

    def test_edit_and_create_pages_go_to_their_list(self):
        self.assertEqual(self.back_for("/gc-admin/skills/4/edit"), "/gc-admin/skills")
        self.assertEqual(self.back_for("/gc-admin/medications/create"), "/gc-admin/medications")
        self.assertEqual(self.back_for("/gc-admin/journal/3/edit"), "/gc-admin/journal")
        self.assertEqual(self.back_for("/gc-admin/tutorials/new"), "/gc-admin/tutorials")
        self.assertEqual(self.back_for("/gc-admin/pdf-library/new"), "/gc-admin/pdf-library")

    def test_personal_pages_go_back_to_today(self):
        self.assertEqual(self.back_for("/gc-admin/me"), "/gc-admin/today")
        self.assertEqual(self.back_for("/gc-admin/medications"), "/gc-admin/today")
        self.assertEqual(self.back_for("/gc-admin/app_ideas"), "/gc-admin/today")

    def test_site_pages_go_back_to_site_dashboard(self):
        self.assertEqual(self.back_for("/gc-admin/skills"), "/gc-admin/")
        self.assertEqual(self.back_for("/gc-admin/now-card"), "/gc-admin/")
        self.assertEqual(self.back_for("/gc-admin/journal"), "/gc-admin/")


if __name__ == "__main__":
    unittest.main()

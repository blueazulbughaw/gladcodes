import unittest
from unittest.mock import patch

from app import create_app
from blueprints.admin.auth import COOKIE_NAME, issue_token
from blueprints.admin.csrf import CSRF_COOKIE_NAME

ROWS = [
    {"id": 1, "category": "Engineering", "skill_name": "Python", "sort_order": 0},
    {"id": 2, "category": "Leadership", "skill_name": "Program management", "sort_order": 1},
    {"id": 3, "category": "Engineering", "skill_name": "Flask", "sort_order": 2},
]


class SkillsAdminTests(unittest.TestCase):
    """Skills admin groups cards by category, same order as /resume."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")

    @patch("blueprints.admin.simple_crud.query", return_value=ROWS)
    def test_list_groups_by_category_in_first_appearance_order(self, _):
        body = self.client.get("/gc-admin/skills").get_data(as_text=True)
        eng, lead = body.index(">Engineering <"), body.index(">Leadership <")
        self.assertLess(eng, lead)
        # Flask (sort_order 2) is listed under Engineering, before the Leadership group
        self.assertLess(body.index("Flask"), lead)
        self.assertEqual(body.count('class="admin-card-group"'), 2)
        self.assertIn("/gc-admin/skills/create?category=Leadership", body)

    def test_add_to_category_prefills_it(self):
        body = self.client.get("/gc-admin/skills/create?category=Leadership").get_data(as_text=True)
        self.assertIn('name="category" value="Leadership"', body)

    @patch("blueprints.admin.simple_crud.execute")
    @patch("blueprints.admin.simple_crud.query_one", return_value={"next": 7})
    def test_new_skill_is_appended_not_put_first(self, _, mock_execute):
        self.client.post("/gc-admin/skills/create", data={"csrf_token": "test-csrf", "category": "Engineering", "skill_name": "Go"})
        sql, params = mock_execute.call_args[0]
        self.assertIn("sort_order", sql)
        self.assertEqual(params, ("Engineering", "Go", 7))


if __name__ == "__main__":
    unittest.main()

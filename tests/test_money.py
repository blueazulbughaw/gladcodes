import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from app import create_app
from blueprints.admin.auth import COOKIE_NAME, issue_token
from blueprints.admin.csrf import CSRF_COOKIE_NAME
from services import money

TODAY = date(2026, 10, 20)


def entry(kind, amount, day=TODAY, category=None, paid_with=None, name=None, note=None, id_=1):
    return {"id": id_, "kind": kind, "amount": Decimal(amount), "entry_date": day, "category": category,
            "paid_with": paid_with, "name": name, "note": note, "bill_id": None}


class MoneyMathTests(unittest.TestCase):
    def test_parse_amount(self):
        self.assertEqual(money.parse_amount("1,234.5"), Decimal("1234.50"))
        self.assertEqual(money.parse_amount(" 20 "), Decimal("20.00"))
        for bad in ("", None, "abc", "0", "-5", "99999999"):
            self.assertIsNone(money.parse_amount(bad), bad)

    def test_parse_month_clamps_to_this_month(self):
        self.assertEqual(money.parse_month("2026-09", TODAY), date(2026, 9, 1))
        self.assertEqual(money.parse_month("2027-01", TODAY), date(2026, 10, 1))
        self.assertEqual(money.parse_month("junk", TODAY), date(2026, 10, 1))

    def test_month_helpers(self):
        self.assertEqual(money.month_bounds(date(2026, 2, 1)), (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(money.shift_month(date(2026, 1, 1), -1), date(2025, 12, 1))
        self.assertEqual(money.shift_month(date(2026, 12, 1), 1), date(2027, 1, 1))
        self.assertEqual(money.due_date(date(2026, 2, 1), 31), date(2026, 2, 28))  # clamped to month end

    def test_card_purchases_are_not_counted_twice(self):
        totals = money.summarize([
            entry("income", "5000"),
            entry("tithe", "500"),
            entry("bill", "300", category="phone"),
            entry("expense", "100", category="food", paid_with="cash"),
            entry("expense", "200", category="groceries", paid_with="card"),  # bought on card
            entry("card", "200"),                                             # paid the card later
        ])
        self.assertEqual(totals["spending"], Decimal("600"))     # 300 bill + 100 + 200 purchases
        self.assertEqual(totals["money_out"], Decimal("1100"))   # 100 cash + 300 + 200 card payment + 500 tithe
        self.assertEqual(totals["left"], Decimal("3900"))
        self.assertEqual(totals["tithe_target"], Decimal("500.00"))
        self.assertEqual(totals["savings_rate"], 78)

    def test_bills_paid_by_card_count_once(self):
        totals = money.summarize([
            entry("income", "1000"),
            entry("bill", "100", category="phone", paid_with="card"),
            entry("card", "100"),
        ])
        self.assertEqual(totals["spending"], Decimal("100"))
        self.assertEqual(totals["card_purchases"], Decimal("100"))
        self.assertEqual(totals["money_out"], Decimal("100"))  # only the card payment left the account

    def test_by_category_and_daily(self):
        rows = money.by_category([entry("expense", "50", category="food"), entry("expense", "30", category="food"),
                                  entry("bill", "100", category="phone"), entry("income", "999")])
        self.assertEqual([(r[0], r[3]) for r in rows], [("phone", Decimal("100")), ("food", Decimal("80"))])
        per_day = money.daily_spending([entry("expense", "12", day=date(2026, 10, 3))], date(2026, 10, 1))
        self.assertEqual(len(per_day), 31)
        self.assertEqual(per_day[date(2026, 10, 3)], Decimal("12"))

    def test_fmt(self):
        self.assertEqual(money.fmt(Decimal("1234.5"), "₱"), "₱1,234.50")
        self.assertEqual(money.fmt(Decimal("-20"), "$"), "-$20.00")


class MoneyPageTests(unittest.TestCase):
    ENTRIES = [
        entry("income", "5000", name="Salary", id_=1),
        entry("expense", "250", category="gas", paid_with="cash", note="Fuel", id_=2),
        entry("expense", "1200", category="groceries", paid_with="card", note="Weekly groceries", id_=3),
        entry("tithe", "300", id_=4),
    ]
    BILLS = [{"id": 9, "name": "Phone plan", "category": "phone", "amount": Decimal("1299"), "due_day": 15, "is_active": 1}]

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            self.client.set_cookie(COOKIE_NAME, issue_token("glad"))
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")
        self.patches = [
            patch("blueprints.admin.money.local_today", return_value=TODAY),
            patch("blueprints.admin.money.money.entries_between", return_value=self.ENTRIES),
            patch("blueprints.admin.money.money.active_bills", return_value=self.BILLS),
            patch("blueprints.admin.money.money.active_cards", return_value=[{"id": 1, "name": "Visa ending 1234", "due_day": 5}]),
            patch("blueprints.admin.money.money.bill_payment", return_value=None),
            patch("blueprints.admin.money.money.currency", return_value="₱"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_entry_page_has_every_section(self):
        body = self.client.get("/gc-admin/finance/ledger").get_data(as_text=True)
        for text in ("Ledger", "Variable expenses", "Income", "Tithes", "Fixed expenses", "Credit card payments", "Net cash flow",
                     "October 2026", "₱5,000.00", "Phone plan", "Due Oct 15", "Visa ending 1234", "Weekly groceries",
                     '<option value="gas">⛽ Gas</option>', '<option value="food">🍔 Food &amp; eating out</option>',
                     'name="entry_date" value="2026-10-20"', '₱300.00 of ₱500.00', 'Payment method', 'Lunch with the team'):
            self.assertIn(text, body)
        self.assertIn('name="robots" content="noindex, nofollow"', body)

    @patch("blueprints.admin.money.money.add_entry")
    def test_add_expense_validates_and_saves(self, add):
        resp = self.client.post("/gc-admin/finance/ledger/add", data={
            "csrf_token": "test-csrf", "kind": "expense", "amount": "1,250.75", "category": "food",
            "paid_with": "card", "entry_date": "2026-10-18", "note": " Lunch "})
        self.assertEqual(resp.status_code, 302)
        args, kwargs = add.call_args
        self.assertEqual(args, ("expense", date(2026, 10, 18), Decimal("1250.75")))
        self.assertEqual((kwargs["category"], kwargs["paid_with"], kwargs["note"]), ("food", "card", "Lunch"))

    @patch("blueprints.admin.money.money.add_entry")
    def test_bad_amount_or_category_never_saves_junk(self, add):
        self.client.post("/gc-admin/finance/ledger/add", data={"csrf_token": "test-csrf", "kind": "expense", "amount": "abc"})
        add.assert_not_called()
        self.client.post("/gc-admin/finance/ledger/add", data={"csrf_token": "test-csrf", "kind": "expense", "amount": "5", "category": "<script>"})
        self.assertEqual(add.call_args.kwargs["category"], "other")
        resp = self.client.post("/gc-admin/finance/ledger/add", data={"csrf_token": "test-csrf", "kind": "hacker", "amount": "5"})
        self.assertEqual(resp.status_code, 400)

    @patch("blueprints.admin.money.money.add_entry")
    def test_ticking_a_bill_records_its_payment(self, add):
        self.client.post("/gc-admin/finance/ledger/bill/9/toggle", data={"csrf_token": "test-csrf", "m": "2026-10", "paid_with": "card"})
        self.assertEqual(add.call_args.args, ("bill", TODAY, Decimal("1299")))
        self.assertEqual(add.call_args.kwargs["bill_id"], 9)
        self.assertEqual(add.call_args.kwargs["paid_with"], "card")

    @patch("blueprints.admin.money.money.delete_entry")
    def test_unticking_a_bill_removes_the_payment(self, delete):
        with patch("blueprints.admin.money.money.bill_payment", return_value={"id": 77}):
            self.client.post("/gc-admin/finance/ledger/bill/9/toggle", data={"csrf_token": "test-csrf", "m": "2026-10"})
        delete.assert_called_once_with(77)

    def test_dashboard_renders_spending_habits(self):
        body = self.client.get("/gc-admin/finance/dashboard").get_data(as_text=True)
        for text in ("Financial dashboard", "Expenses by category", "Daily expenses", "Income vs expenses", "Fixed expenses this month",
                     "Largest transactions", "Total expenses", "savings rate", "Groceries<span class=\"money-cat-bar\">", "83%", "₱4,450.00",
                     "On credit card ₱1,200.00", "Cash / debit ₱250.00"):
            self.assertIn(text, body)

    def test_pages_are_private_and_posts_need_csrf(self):
        anon = self.app.test_client()
        for path in ("/gc-admin/finance/ledger", "/gc-admin/finance/dashboard"):
            self.assertEqual(anon.get(path).status_code, 302)
        resp = self.client.post("/gc-admin/finance/ledger/add", data={"kind": "expense", "amount": "5"})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()

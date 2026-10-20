"""Personal money tracker (/gc-admin/money + /gc-admin/money/dashboard).

Modeled on how established trackers (YNAB, Monarch, Copilot, Goodbudget)
handle the same things:
- Every entry is a transaction: date (defaults to the day it's entered),
  amount, category, optional note.
- Recurring monthly bills are their own list (name, category, amount, due
  day) and get ticked "paid" each month, creating that month's transaction.
- Credit cards: a purchase or a monthly bill paid on a card is *spending* on
  the day it's made (paid_with='card'); paying the card bill later is a
  *card payment*. Spending
  habits count purchases; cash flow counts money actually leaving (cash/debit
  spending + bills + card payments), so nothing is counted twice.
- Tithes are tracked against 10% of the month's earnings.
Private: nothing in blueprints/public reads these tables.
"""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from database.db import execute, query, query_one, utc_now

KINDS = ("income", "tithe", "bill", "card", "expense")

EXPENSE_CATEGORIES = [
    ("food", "🍔", "Food & eating out"),
    ("groceries", "🛒", "Groceries"),
    ("gas", "⛽", "Gas"),
    ("transport", "🚗", "Transportation & parking"),
    ("shopping", "🛍️", "Shopping"),
    ("household", "🏠", "Household"),
    ("health", "💊", "Health & medicine"),
    ("personal", "💅", "Personal care"),
    ("entertainment", "🎬", "Entertainment"),
    ("giving", "🎁", "Gifts & giving"),
    ("family", "👨‍👩‍👧", "Family"),
    ("travel", "✈️", "Travel"),
    ("other", "📦", "Other"),
]
BILL_CATEGORIES = [
    ("phone", "📱", "Phone"),
    ("car_insurance", "🚙", "Car insurance"),
    ("rent", "🏡", "Rent / mortgage"),
    ("utilities", "💡", "Utilities"),
    ("internet", "🌐", "Internet"),
    ("subscriptions", "📺", "Subscriptions"),
    ("insurance", "🛡️", "Other insurance"),
    ("loan", "🏦", "Loan"),
    ("other_bill", "🧾", "Other fixed expense"),
]
CATEGORY = {key: (emoji, label) for key, emoji, label in EXPENSE_CATEGORIES + BILL_CATEGORIES}
PAID_WITH = ("cash", "card")
TITHE_RATE = Decimal("0.10")
MAX_AMOUNT = Decimal("10000000")
CURRENCIES = ["$", "₱", "€", "£", "¥", "₩", "₹", "A$", "C$", "S$"]


# --- pure helpers (unit-tested) -------------------------------------------

def parse_amount(raw):
    """'1,234.50' -> Decimal('1234.50'); None for blank, invalid, <= 0 or huge."""
    try:
        value = Decimal(str(raw or "").replace(",", "").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return value if Decimal("0") < value <= MAX_AMOUNT else None


def parse_month(raw, today):
    """'2026-09' -> date(2026, 9, 1); anything else (or a future month) -> this month."""
    try:
        year, month = (int(x) for x in (raw or "").split("-"))
        first = date(year, month, 1)
    except (ValueError, TypeError):
        first = today.replace(day=1)
    return min(first, today.replace(day=1))


def month_bounds(first):
    nxt = (first + timedelta(days=32)).replace(day=1)
    return first, nxt - timedelta(days=1)


def shift_month(first, months):
    y, m = first.year, first.month - 1 + months
    return date(y + m // 12, m % 12 + 1, 1)


def due_date(first, due_day):
    """The bill's due date inside the month starting at `first` (clamped to month end)."""
    _, last = month_bounds(first)
    return first.replace(day=max(1, min(int(due_day or 1), last.day)))


def summarize(entries):
    """Month totals. `spending` = what you bought (daily expenses + bills,
    however paid); `money_out` = what actually left (cash/debit expenses and
    bills + card payments + tithes), so anything bought or billed on a credit
    card is only counted once: when the card bill is paid."""
    t = {kind: Decimal("0") for kind in KINDS}
    card_purchases = Decimal("0")
    for e in entries:
        t[e["kind"]] += Decimal(e["amount"])
        if e["kind"] in ("expense", "bill") and e.get("paid_with") == "card":
            card_purchases += Decimal(e["amount"])
    spending = t["expense"] + t["bill"]
    money_out = (t["expense"] + t["bill"] - card_purchases) + t["card"] + t["tithe"]
    income = t["income"]
    return {
        "income": income,
        "tithe": t["tithe"],
        "bills": t["bill"],
        "card_payments": t["card"],
        "expenses": t["expense"],
        "card_purchases": card_purchases,
        "spending": spending,
        "money_out": money_out,
        "left": income - money_out,
        "tithe_target": (income * TITHE_RATE).quantize(Decimal("0.01")),
        "savings_rate": round(float((income - money_out) / income * 100)) if income else None,
    }


def by_category(entries):
    """[(key, emoji, label, total)] for spending (expenses + bills), biggest first."""
    totals = {}
    for e in entries:
        if e["kind"] in ("expense", "bill"):
            totals[e["category"]] = totals.get(e["category"], Decimal("0")) + Decimal(e["amount"])
    rows = [(k, *CATEGORY.get(k, ("📦", k.replace("_", " ").title())), v) for k, v in totals.items()]
    return sorted(rows, key=lambda r: r[3], reverse=True)


def daily_spending(entries, first):
    """Spending (expenses + bills) per day of the month, for the bar chart."""
    _, last = month_bounds(first)
    per_day = {first + timedelta(days=i): Decimal("0") for i in range(last.day)}
    for e in entries:
        if e["kind"] in ("expense", "bill") and e["entry_date"] in per_day:
            per_day[e["entry_date"]] += Decimal(e["amount"])
    return per_day


def fmt(amount, currency):
    amount = Decimal(amount or 0)
    sign = "-" if amount < 0 else ""
    return f"{sign}{currency}{abs(amount):,.2f}"


# --- DB helpers -------------------------------------------------------------

def entries_between(start, end):
    return query(
        "SELECT * FROM money_entries WHERE entry_date BETWEEN %s AND %s ORDER BY entry_date DESC, id DESC",
        (start, end),
    )


def add_entry(kind, entry_date, amount, category=None, name=None, note=None, paid_with=None, bill_id=None):
    execute(
        """
        INSERT INTO money_entries (kind, entry_date, amount, category, name, note, paid_with, bill_id, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (kind, entry_date, amount, category, name, note, paid_with, bill_id, utc_now()),
    )


def delete_entry(entry_id: int) -> None:
    execute("DELETE FROM money_entries WHERE id = %s", (entry_id,))


def active_bills():
    return query("SELECT * FROM recurring_bills WHERE is_active = 1 ORDER BY due_day, sort_order, id")


def active_cards():
    return query("SELECT * FROM credit_cards WHERE is_active = 1 ORDER BY sort_order, id")


def bill_payment(bill_id: int, first):
    start, end = month_bounds(first)
    return query_one(
        "SELECT * FROM money_entries WHERE kind = 'bill' AND bill_id = %s AND entry_date BETWEEN %s AND %s",
        (bill_id, start, end),
    )


def currency() -> str:
    row = query_one("SELECT money_currency FROM checkin_app_state WHERE id = 1")
    return (row or {}).get("money_currency") or "$"


def set_currency(symbol: str) -> None:
    if symbol in CURRENCIES:
        execute("UPDATE checkin_app_state SET money_currency = %s WHERE id = 1", (symbol,))

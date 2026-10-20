"""Financial: the Ledger, a one-page entry form like Today
(/gc-admin/finance/ledger), and the Financial dashboard
(/gc-admin/finance/dashboard). See services/money.py for how
spending vs. cash flow is counted (credit cards aren't double-counted)."""
from datetime import date
from decimal import Decimal

from flask import abort, redirect, render_template, request, url_for

from services import money

from . import admin_bp
from .checkin import local_today


def _month_url(endpoint, first, anchor=""):
    return url_for(endpoint, m=first.strftime("%Y-%m")) + (f"#{anchor}" if anchor else "")


def _entry_date(raw, today):
    try:
        return date.fromisoformat(raw or "")
    except ValueError:
        return today


def _month_context(first, today):
    """Shared by the entry page and the dashboard: entries + totals."""
    start, end = money.month_bounds(first)
    entries = money.entries_between(start, end)
    return entries, money.summarize(entries)


@admin_bp.app_template_filter("money")
def money_filter(amount, symbol="$"):
    return money.fmt(amount, symbol)


@admin_bp.route("/finance/ledger")
def money_index():
    today = local_today()
    first = money.parse_month(request.args.get("m"), today)
    entries, totals = _month_context(first, today)
    is_current = first == today.replace(day=1)
    _, last = money.month_bounds(first)

    bills = []
    for bill in money.active_bills():
        bills.append({**bill, "due": money.due_date(first, bill["due_day"]), "payment": money.bill_payment(bill["id"], first)})
    cards = money.active_cards()
    by_kind = {kind: [e for e in entries if e["kind"] == kind] for kind in money.KINDS}

    return render_template(
        "money.html",
        first=first,
        prev_month=money.shift_month(first, -1),
        next_month=money.shift_month(first, 1) if not is_current else None,
        default_date=today if is_current else last,
        today=today,
        totals=totals,
        by_kind=by_kind,
        bills=bills,
        cards=cards,
        expense_categories=money.EXPENSE_CATEGORIES,
        category=money.CATEGORY,
        currency=money.currency(),
        currencies=money.CURRENCIES,
    )


@admin_bp.route("/finance/ledger/add", methods=["POST"])
def money_add():
    today = local_today()
    kind = request.form.get("kind", "")
    if kind not in ("income", "tithe", "card", "expense"):
        abort(400)
    amount = money.parse_amount(request.form.get("amount"))
    when = _entry_date(request.form.get("entry_date"), today)
    first = when.replace(day=1)
    if amount is None:
        return redirect(_month_url("admin.money_index", min(first, today.replace(day=1)), kind))
    category = request.form.get("category") or None
    if kind == "expense" and category not in dict((k, l) for k, _, l in money.EXPENSE_CATEGORIES):
        category = "other"
    paid_with = request.form.get("paid_with") if kind == "expense" else None
    if paid_with not in money.PAID_WITH:
        paid_with = "cash" if kind == "expense" else None
    name = (request.form.get("name") or "").strip()[:255] or None
    note = (request.form.get("note") or "").strip()[:1000] or None
    money.add_entry(kind, when, amount, category=category if kind == "expense" else None,
                    name=name, note=note, paid_with=paid_with)
    return redirect(_month_url("admin.money_index", min(first, today.replace(day=1)), kind))


@admin_bp.route("/finance/ledger/entry/<int:entry_id>/delete", methods=["POST"])
def money_delete(entry_id):
    money.delete_entry(entry_id)
    return redirect(url_for("admin.money_index", m=request.form.get("m")) + "#" + (request.form.get("kind") or ""))


@admin_bp.route("/finance/ledger/bill/<int:bill_id>/toggle", methods=["POST"])
def money_bill_toggle(bill_id):
    """Tick a recurring bill paid for the month (records that month's
    payment at the bill's amount), or untick it (removes the payment)."""
    today = local_today()
    first = money.parse_month(request.form.get("m"), today)
    existing = money.bill_payment(bill_id, first)
    if existing:
        money.delete_entry(existing["id"])
    else:
        bill = next((b for b in money.active_bills() if b["id"] == bill_id), None)
        if bill is None:
            abort(404)
        amount = money.parse_amount(request.form.get("amount")) or Decimal(bill["amount"])
        when = today if first == today.replace(day=1) else money.due_date(first, bill["due_day"])
        paid_with = request.form.get("paid_with")
        if paid_with not in money.PAID_WITH:
            paid_with = bill.get("paid_with") or "cash"
        money.add_entry("bill", when, amount, category=bill["category"], name=bill["name"],
                        paid_with=paid_with, bill_id=bill_id)
    return redirect(_month_url("admin.money_index", first, "bills"))


@admin_bp.route("/finance/ledger/currency", methods=["POST"])
def money_currency():
    money.set_currency(request.form.get("currency", ""))
    return redirect(url_for("admin.money_index", m=request.form.get("m")))


@admin_bp.route("/finance/dashboard")
def money_dashboard():
    today = local_today()
    first = money.parse_month(request.args.get("m"), today)
    entries, totals = _month_context(first, today)
    is_current = first == today.replace(day=1)

    categories = money.by_category(entries)
    prev_first = money.shift_month(first, -1)
    prev_entries, prev_totals = _month_context(prev_first, today)
    prev_by_cat = {k: total for k, _, _, total in money.by_category(prev_entries)}
    spending_total = totals["spending"] or Decimal("0")
    category_rows = [
        {"key": k, "emoji": emoji, "label": label, "total": total,
         "share": round(float(total / spending_total * 100)) if spending_total else 0,
         "change": (total - prev_by_cat.get(k, Decimal("0")))}
        for k, emoji, label, total in categories
    ]

    per_day = money.daily_spending(entries, first)
    days_so_far = today.day if is_current else len(per_day)
    expenses = [e for e in entries if e["kind"] == "expense"]

    trend = []
    for i in range(5, -1, -1):
        m = money.shift_month(first, -i)
        _, t = _month_context(m, today)
        trend.append({"label": m.strftime("%b"), "income": t["income"], "spending": t["spending"], "out": t["money_out"]})

    bills = [{**b, "due": money.due_date(first, b["due_day"]), "payment": money.bill_payment(b["id"], first)}
             for b in money.active_bills()]

    return render_template(
        "money_dashboard.html",
        first=first,
        prev_month=prev_first,
        next_month=money.shift_month(first, 1) if not is_current else None,
        today=today,
        totals=totals,
        prev_totals=prev_totals,
        category_rows=category_rows,
        avg_daily=(totals["expenses"] / days_so_far) if days_so_far else Decimal("0"),
        cash_spend=totals["spending"] - totals["card_purchases"],
        biggest=sorted(expenses, key=lambda e: Decimal(e["amount"]), reverse=True)[:5],
        bills=bills,
        category=money.CATEGORY,
        currency=money.currency(),
        chart={
            "cat_labels": [f"{r['emoji']} {r['label']}" for r in category_rows],
            "cat_data": [float(r["total"]) for r in category_rows],
            "day_labels": [str(d.day) for d in per_day],
            "day_data": [float(v) if d <= today else None for d, v in per_day.items()],
            "trend_labels": [t["label"] for t in trend],
            "trend_income": [float(t["income"]) for t in trend],
            "trend_spending": [float(t["spending"]) for t in trend],
        },
    )

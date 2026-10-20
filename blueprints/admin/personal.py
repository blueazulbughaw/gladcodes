"""Personal dashboard (/gc-admin/me): everything from the daily check-in
and the phone, kept separate from the website CMS dashboard (/gc-admin/).
Weekly (Sunday-Saturday) or monthly view: an emoji/check grid (mood, energy,
prayers, devotion, medicines, water, movement, period, meals, learnings),
mood/energy/sleep/Instagram graphs, and the period cycle. No sentences here
by request: tapping a day opens that day's check-in with everything written.

Also the phone-automation endpoints (/gc-admin/track/*), authenticated by a
bearer token instead of the JWT cookie, since an iPhone Shortcut / Android
automation has no browser session.
"""
from datetime import timedelta

from flask import abort, current_app, jsonify, redirect, render_template, request, url_for

from database.db import query
from services import tracking
from services.github import configured_username, get_weekly_activity

from . import admin_bp
from .checkin import MOODS, checkin_streak, current_streak, local_today, local_tz_name, parse_day

ENERGY_EMOJI = {1: "🪫", 2: "😴", 3: "🙂", 4: "💪", 5: "⚡"}
VIEWS = ("week", "month")


def _series(by_day, days, key):
    return [
        float(by_day[d][key]) if d in by_day and by_day[d][key] is not None else None
        for d in days
    ]


def period_days(view, anchor):
    """(days, prev_anchor, next_anchor) for the week (Sunday-Saturday) or the
    calendar month containing `anchor`."""
    if view == "month":
        first = anchor.replace(day=1)
        nxt = (first + timedelta(days=32)).replace(day=1)
        days = [first + timedelta(days=i) for i in range((nxt - first).days)]
        return days, (first - timedelta(days=1)).replace(day=1), nxt
    start = anchor - timedelta(days=(anchor.weekday() + 1) % 7)  # back to Sunday
    days = [start + timedelta(days=i) for i in range(7)]
    return days, start - timedelta(days=7), start + timedelta(days=7)


def _check(value):
    return {"text": "✓", "state": "done"} if value else {"text": "", "state": "empty"}


def medicine_cell(med, day, taken):
    """Checks only: ✓ all doses, amber ✓ some, empty if missed, blank if not due."""
    got = len(taken.get((med["id"], day), ()))
    if not tracking.medication_due(med, day) or med["frequency"] == "as_needed":
        return {"text": "✓", "state": "done"} if got else {"text": "", "state": "off"}
    if got >= tracking.dose_count(med):
        return {"text": "✓", "state": "done"}
    return {"text": "✓", "state": "part"} if got else {"text": "", "state": "missed"}


def build_grid(days, by_day, meds, taken, today):
    """Rows of emoji/check cells, one column per day, for the dashboard grid.
    No sentences: the words live on each day's check-in (tap the day)."""
    mood_emoji = {value: emoji for value, emoji, _ in MOODS}

    def row(emoji, label, cell_fn):
        cells = []
        for d in days:
            entry = by_day.get(d)
            if d > today:
                cells.append({"text": "", "state": "future"})
            else:
                cells.append(cell_fn(d, entry))
        return {"emoji": emoji, "label": label, "cells": cells}

    def field(key):
        return lambda d, e: _check(e and e[key])

    rows = [
        row("😊", "Mood", lambda d, e: {"text": mood_emoji.get(e["mood"], ""), "state": "emoji"} if e and e["mood"] else {"text": "", "state": "empty"}),
        row("⚡", "Energy", lambda d, e: {"text": ENERGY_EMOJI.get(e["energy"], ""), "state": "emoji"} if e and e["energy"] else {"text": "", "state": "empty"}),
        # A prayer counts when it's written (older days also used a checkbox).
        row("🙏", "Morning prayer", lambda d, e: _check(e and (e["morning_prayer_note"] or e["morning_prayer"]))),
        row("📖", "Devotion", lambda d, e: _check(e and (e["bible_passage"] or e["devotion_thoughts"]))),
    ]
    for med in meds:
        rows.append(row("💊", med["name"], lambda d, e, med=med: medicine_cell(med, d, taken)))
    rows += [
        row("💧", "Water", lambda d, e: {"text": str(e["water_glasses"]), "state": "water-%d" % min(8, e["water_glasses"])} if e and e["water_glasses"] else {"text": "", "state": "empty"}),
        row("🏃", "Moved", field("exercised")),
        row("🩸", "Period", lambda d, e: {"text": "🩸", "state": "emoji"} if e and e["period_day"] else {"text": "", "state": "empty"}),
        row("🍳", "Breakfast", field("food_breakfast")),
        row("🥗", "Lunch", field("food_lunch")),
        row("🍲", "Dinner", field("food_dinner")),
        row("🍎", "Snacks", field("food_snacks")),
        row("📚", "Learnings", lambda d, e: _check(e and (e["reading"] or e["learnings"] or e["win"]))),
        row("🌙", "Evening prayer", lambda d, e: _check(e and (e["night_prayer_note"] or e["night_prayer"]))),
    ]
    return rows


@admin_bp.route("/me")
def personal_dashboard():
    today = local_today()
    tz_name = local_tz_name()
    view = request.args.get("view") if request.args.get("view") in VIEWS else "week"
    anchor = parse_day(request.args.get("d"), today)
    days, prev_anchor, next_anchor = period_days(view, anchor)
    past = [d for d in days if d <= today]

    rows = query(
        "SELECT * FROM daily_checkins WHERE checkin_date BETWEEN %s AND %s ORDER BY checkin_date",
        (days[0], days[-1]),
    )
    by_day = {row["checkin_date"]: row for row in rows}
    sleep = tracking.sleep_by_day(past)
    app_minutes = tracking.app_minutes_by_day(tracking.TRACKED_APP, past, tz_name)
    meds = tracking.active_medications()
    grid = build_grid(days, by_day, meds, tracking.doses_taken(days[0], days[-1]), today)

    prayer_days = [r["checkin_date"] for r in query(
        "SELECT checkin_date FROM daily_checkins WHERE morning_prayer = 1 AND night_prayer = 1 AND checkin_date <= %s",
        (today,),
    )]
    period_sleep = [sleep[d] for d in past if d in sleep]
    period_water = [by_day[d]["water_glasses"] for d in past if d in by_day]
    period_app = [app_minutes.get(d, 0) for d in past]

    period_rows = query("SELECT checkin_date FROM daily_checkins WHERE period_day = 1")
    periods = tracking.periods_from_days([r["checkin_date"] for r in period_rows])
    cycle = tracking.cycle_summary(periods, today)

    short = "%a" if view == "week" else "%d"
    return render_template(
        "me.html",
        view=view,
        days=days,
        today=today,
        title=(f"{days[0]:%b} {days[0].day} – {days[-1]:%b} {days[-1].day}" if view == "week" else f"{days[0]:%B %Y}"),
        prev_anchor=prev_anchor,
        next_anchor=next_anchor if next_anchor <= today else None,
        grid=grid,
        streak=checkin_streak(today),
        # GitHub pushes this week (Monday-start buckets from services/github);
        # None when GitHub is unreachable, so the tile just shows a dash.
        github_pushes=(lambda g: g["data"][-1] if g else None)(get_weekly_activity(configured_username())),
        prayer_streak=current_streak(prayer_days, today),
        avg_sleep=round(sum(period_sleep) / len(period_sleep)) if period_sleep else None,
        avg_water=round(sum(period_water) / len(period_water), 1) if period_water else None,
        avg_app=round(sum(period_app) / len(period_app)) if any(period_app) else None,
        tracked_app=tracking.TRACKED_APP,
        chart={
            "labels": [d.strftime(short).lstrip("0") for d in days],
            "mood": _series(by_day, days, "mood"),
            "energy": _series(by_day, days, "energy"),
            "sleep": [round(sleep[d] / 60, 1) if d in sleep else None for d in days],
            "app": [app_minutes.get(d) if d <= today else None for d in days],
            "mood_ticks": {str(v): e for v, e, _ in MOODS},
            "energy_ticks": {str(k): v for k, v in ENERGY_EMOJI.items()},
        },
        periods=list(reversed(periods))[:6],
        cycle=cycle,
        token=tracking.ingest_token(),
        site_base=current_app.config["PUBLIC_SITE_URL"].rstrip("/"),
        status=tracking.tracking_status(),
    )


@admin_bp.route("/me/regenerate-token", methods=["POST"])
def regenerate_tracking_token():
    tracking.regenerate_ingest_token()
    return redirect(url_for("admin.personal_dashboard") + "#tracking")


# --- phone automations ------------------------------------------------------

def _require_token():
    header = request.headers.get("Authorization", "")
    presented = header[7:].strip() if header.startswith("Bearer ") else ""
    if not tracking.token_matches(presented):
        abort(404)  # same as any unknown URL: reveal nothing


def _payload():
    return request.get_json(silent=True) or request.form


@admin_bp.route("/track/sleep", methods=["POST"])
def track_sleep():
    """Either {"event": "start" | "end"} from a phone automation on Sleep /
    bedtime mode turning on and off (the server works out the hours), or a
    finished night: {"hours": 7.25} / {"minutes": 435}, optional "date"
    (YYYY-MM-DD, defaults to today = the morning you woke up)."""
    _require_token()
    data = _payload()
    event = (data.get("event") or "").strip().lower()
    if event in ("start", "end"):
        minutes = tracking.record_sleep_event(event, local_today())
        return jsonify({"ok": True, "minutes": minutes})
    try:
        if data.get("minutes") not in (None, ""):
            minutes = round(float(data["minutes"]))
        else:
            minutes = round(float(data.get("hours")) * 60)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "send hours or minutes"}), 400
    if not 0 <= minutes <= 24 * 60:
        return jsonify({"ok": False, "error": "out of range"}), 400
    today = local_today()
    tracking.record_sleep(parse_day(data.get("date"), today), minutes)
    return jsonify({"ok": True})


@admin_bp.route("/track/app", methods=["POST"])
def track_app():
    """{"event": "opened" | "closed"} — sent by a phone automation when the
    tracked app (Instagram) opens or closes. Optional "app" name."""
    _require_token()
    data = _payload()
    event = (data.get("event") or "").strip().lower()
    if event not in ("opened", "closed"):
        return jsonify({"ok": False, "error": "event must be opened or closed"}), 400
    app = (data.get("app") or tracking.TRACKED_APP).strip()[:64]
    tracking.record_app_event(app, event)
    return jsonify({"ok": True})

"""Private daily check-in (/gc-admin/today): mood, ADHD trackers, what I
read, what I'm thankful for. Login lands here until today's entry exists,
so the site is the first thing I open in the morning instead of Instagram.

Never exposed publicly — nothing here is read by blueprints/public.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pymysql
from flask import current_app, redirect, render_template, request, url_for

from database.db import execute, query, query_one, utc_now
from services.github import configured_username, get_weekly_activity

from . import admin_bp

MOODS = [(1, "😞", "Rough"), (2, "😕", "Meh"), (3, "😐", "Okay"), (4, "🙂", "Good"), (5, "😄", "Great")]
CHART_DAYS = 14


def valid_timezone(name) -> bool:
    if not name or len(name) > 64:
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def saved_timezone():
    """The timezone the phone/browser last reported (see save_timezone), so
    LOCAL_TIMEZONE never has to be configured by hand."""
    try:
        row = query_one("SELECT local_timezone FROM checkin_app_state WHERE id = 1")
    except pymysql.err.MySQLError:  # table not created yet, DB unreachable in tests
        return None
    return row["local_timezone"] if row else None


def save_timezone(name) -> None:
    if valid_timezone(name):
        execute("UPDATE checkin_app_state SET local_timezone = %s WHERE id = 1", (name,))


def local_now() -> datetime:
    name = saved_timezone() or current_app.config["LOCAL_TIMEZONE"]
    return datetime.now(ZoneInfo(name) if valid_timezone(name) else ZoneInfo("UTC"))


def local_today() -> date:
    return local_now().date()


def has_checked_in(day: date) -> bool:
    return query_one("SELECT id FROM daily_checkins WHERE checkin_date = %s", (day,)) is not None


def current_streak(dates, today: date) -> int:
    """Consecutive check-in days ending today — or yesterday, so the streak
    doesn't read as broken first thing in the morning before I've checked in."""
    have = set(dates)
    day = today if today in have else today - timedelta(days=1)
    streak = 0
    while day in have:
        streak += 1
        day -= timedelta(days=1)
    return streak


def parse_day(value, today: date) -> date:
    """A YYYY-MM-DD from the URL/form, or today. Future dates aren't allowed."""
    try:
        day = date.fromisoformat(value or "")
    except ValueError:
        return today
    return day if day <= today else today


def _scale(name):
    value = request.form.get(name, "")
    return int(value) if value in {"1", "2", "3", "4", "5"} else None


def _number(name, cast, low, high):
    try:
        value = cast(request.form.get(name, ""))
    except ValueError:
        return None
    return value if low <= value <= high else None


def _text(name, max_len=None):
    value = request.form.get(name, "").strip()
    return (value[:max_len] if max_len else value) or None


def hour_label(hour: int) -> str:
    return f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"


def _flag(name):
    return 1 if request.form.get(name) else 0


def checkin_streak(today: date):
    dates = [row["checkin_date"] for row in query(
        "SELECT checkin_date FROM daily_checkins WHERE checkin_date <= %s ORDER BY checkin_date DESC LIMIT 400",
        (today,),
    )]
    return current_streak(dates, today)


@admin_bp.route("/today", methods=["GET", "POST"])
def today():
    today_date = local_today()

    if request.method == "POST":
        save_timezone(request.form.get("tz"))
        day = parse_day(request.form.get("checkin_date"), today_date)
        execute(
            """
            INSERT INTO daily_checkins
                (checkin_date, mood, energy, focus, sleep_hours, took_meds, exercised,
                 reading, grateful, top_priority, priority_done, scroll_minutes, win, notes, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                mood = VALUES(mood), energy = VALUES(energy), focus = VALUES(focus),
                sleep_hours = VALUES(sleep_hours), took_meds = VALUES(took_meds),
                exercised = VALUES(exercised), reading = VALUES(reading),
                grateful = VALUES(grateful), top_priority = VALUES(top_priority),
                priority_done = VALUES(priority_done), scroll_minutes = VALUES(scroll_minutes),
                win = VALUES(win), notes = VALUES(notes), updated_at = VALUES(updated_at)
            """,
            (
                day,
                _scale("mood"),
                _scale("energy"),
                _scale("focus"),
                _number("sleep_hours", float, 0, 24),
                _flag("took_meds"),
                _flag("exercised"),
                _text("reading"),
                _text("grateful"),
                _text("top_priority", 255),
                _flag("priority_done"),
                _number("scroll_minutes", int, 0, 1440),
                _text("win"),
                _text("notes"),
                utc_now(),
            ),
        )
        if day == today_date:
            return redirect(url_for("admin.today", saved=1))
        return redirect(url_for("admin.today", date=day.isoformat(), saved=1))

    day = parse_day(request.args.get("date"), today_date)
    entry = query_one("SELECT * FROM daily_checkins WHERE checkin_date = %s", (day,))

    chart_start = today_date - timedelta(days=CHART_DAYS - 1)
    rows = query(
        "SELECT checkin_date, mood, energy, focus, sleep_hours, scroll_minutes FROM daily_checkins WHERE checkin_date >= %s",
        (chart_start,),
    )
    by_day = {row["checkin_date"]: row for row in rows}
    chart_days = [chart_start + timedelta(days=i) for i in range(CHART_DAYS)]

    def series(key):
        return [
            float(by_day[d][key]) if d in by_day and by_day[d][key] is not None else None
            for d in chart_days
        ]

    chart = {
        "labels": [d.strftime("%b %d") for d in chart_days],
        "mood": series("mood"),
        "energy": series("energy"),
        "focus": series("focus"),
        "scroll": series("scroll_minutes"),
    }

    history = query(
        """
        SELECT checkin_date, mood, reading, grateful, top_priority, priority_done, win
        FROM daily_checkins ORDER BY checkin_date DESC LIMIT 30
        """
    )

    hour = local_now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"

    return render_template(
        "today.html",
        day=day,
        is_today=day == today_date,
        entry=entry,
        greeting=greeting,
        streak=checkin_streak(today_date),
        moods=MOODS,
        chart=chart,
        history=history,
        github=get_weekly_activity(configured_username()),
        vapid_public_key=current_app.config.get("VAPID_PUBLIC_KEY") or None,
        morning_hour=hour_label(current_app.config["CHECKIN_MORNING_HOUR"]),
        evening_hour=hour_label(current_app.config["CHECKIN_EVENING_HOUR"]),
        saved=request.args.get("saved") == "1",
    )

"""Private daily check-in (/gc-admin/today): prayers, mood + why, energy,
gratitude, medicine doses, devotion (Bible passage + thoughts), learnings
(reading, learnings, wins, notes), body
(water, movement, period day), the food log (breakfast, lunch, dinner,
snacks), the evening prayer, and My emotions
(mood, why, energy, gratitude). Autosaves: no Save button.
Sleep and Instagram time are shown but never typed; the phone sends them
(personal.py /track/*). Login lands here until today's entry exists.

Never exposed publicly — nothing here is read by blueprints/public.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pymysql
from flask import current_app, jsonify, redirect, render_template, request, url_for

from database.db import execute, query, query_one, utc_now
from services import tracking
from services.github import configured_username, get_weekly_activity

from . import admin_bp

MOODS = [(1, "😞", "Rough"), (2, "😕", "Meh"), (3, "😐", "Okay"), (4, "🙂", "Good"), (5, "😄", "Great")]


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


def local_tz_name() -> str:
    name = saved_timezone() or current_app.config["LOCAL_TIMEZONE"]
    return name if valid_timezone(name) else "UTC"


def local_now() -> datetime:
    return datetime.now(ZoneInfo(local_tz_name()))


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


def _text(name, max_len=None):
    value = request.form.get(name, "").strip()
    return (value[:max_len] if max_len else value) or None


def hour_label(hour: int) -> str:
    return f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"


def _water() -> int:
    """Glasses of water: how many of the 8 glass checkboxes are ticked."""
    return len({v for v in request.form.getlist("water") if v in {str(n) for n in range(1, 9)}})


def _flag(name):
    return 1 if request.form.get(name) else 0


def checkin_streak(today: date):
    dates = [row["checkin_date"] for row in query(
        "SELECT checkin_date FROM daily_checkins WHERE checkin_date <= %s ORDER BY checkin_date DESC LIMIT 400",
        (today,),
    )]
    return current_streak(dates, today)


CHECKIN_FIELDS = (
    "mood", "mood_reason", "energy", "morning_prayer", "night_prayer", "exercised",
    "period_day", "reading", "learnings", "bible_passage", "grateful", "win", "notes",
    "morning_prayer_note", "water_glasses", "night_prayer_note", "devotion_thoughts",
    "food_breakfast", "food_lunch", "food_dinner", "food_snacks",
)


def _checkin_values():
    """Today form → column values, in CHECKIN_FIELDS order."""
    return (
        _scale("mood"),
        _text("mood_reason"),
        _scale("energy"),
        # No checkboxes for prayers any more: writing a prayer is what counts.
        1 if _text("morning_prayer_note") else 0,
        1 if _text("night_prayer_note") else 0,
        _flag("exercised"),
        _flag("period_day"),
        _text("reading"),
        _text("learnings"),
        _text("bible_passage"),
        _text("grateful"),
        _text("win"),
        _text("notes"),
        _text("morning_prayer_note"),
        _water(),
        _text("night_prayer_note"),
        _text("devotion_thoughts"),
        _text("food_breakfast"),
        _text("food_lunch"),
        _text("food_dinner"),
        _text("food_snacks"),
    )


def save_checkin(day: date) -> None:
    columns = ", ".join(CHECKIN_FIELDS)
    placeholders = ", ".join(["%s"] * (len(CHECKIN_FIELDS) + 2))
    updates = ", ".join(f"{c} = VALUES({c})" for c in CHECKIN_FIELDS + ("updated_at",))
    # Column names come from the fixed CHECKIN_FIELDS tuple above, never input.
    execute(
        f"""
        INSERT INTO daily_checkins (checkin_date, {columns}, updated_at)
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE {updates}
        """,
        (day, *_checkin_values(), utc_now()),
    )


def _wants_json() -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


@admin_bp.route("/today", methods=["GET", "POST"])
def today():
    today_date = local_today()

    if request.method == "POST":
        # Autosave: the page posts the whole form in the background on every
        # change (no Save button). The <noscript> fallback does a normal post.
        save_timezone(request.form.get("tz"))
        day = parse_day(request.form.get("checkin_date"), today_date)
        save_checkin(day)
        if _wants_json():
            return jsonify({"ok": True})
        if day == today_date:
            return redirect(url_for("admin.today"))
        return redirect(url_for("admin.today", date=day.isoformat()))

    day = parse_day(request.args.get("date"), today_date)
    entry = query_one("SELECT * FROM daily_checkins WHERE checkin_date = %s", (day,))

    taken = tracking.doses_taken(day, day)
    medications = [
        {
            "id": med["id"],
            "name": med["name"],
            "notes": med["notes"],
            "frequency": med["frequency"],
            "doses": [(i, i in taken.get((med["id"], day), set())) for i in range(1, tracking.dose_count(med) + 1)],
        }
        for med in tracking.active_medications()
        if tracking.medication_due(med, day)
    ]

    tz_name = local_tz_name()
    sleep_minutes = tracking.sleep_by_day([day]).get(day)
    app_minutes = tracking.app_minutes_by_day(tracking.TRACKED_APP, [day], tz_name).get(day, 0)
    has_tracking = tracking.tracking_status()

    hour = local_now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"

    return render_template(
        "today.html",
        day=day,
        is_today=day == today_date,
        # Day navigation: edit any past day (forgot something yesterday?).
        prev_day=day - timedelta(days=1),
        next_day=day + timedelta(days=1) if day < today_date else None,
        today_date=today_date,
        entry=entry,
        greeting=greeting,
        streak=checkin_streak(today_date),
        moods=MOODS,
        medications=medications,
        sleep_minutes=sleep_minutes,
        app_minutes=app_minutes,
        tracked_app=tracking.TRACKED_APP,
        tracking_connected=bool(has_tracking["last_sleep"] or has_tracking["last_app"]),
        github=get_weekly_activity(configured_username()),
        vapid_public_key=current_app.config.get("VAPID_PUBLIC_KEY") or None,
        morning_hour=hour_label(current_app.config["CHECKIN_MORNING_HOUR"]),
        evening_hour=hour_label(current_app.config["CHECKIN_EVENING_HOUR"]),
    )


@admin_bp.route("/today/dose", methods=["POST"])
def today_dose():
    """One medicine checkbox, saved the moment it's ticked/unticked."""
    day = parse_day(request.form.get("checkin_date"), local_today())
    try:
        medication_id = int(request.form.get("medication_id", ""))
        dose_index = int(request.form.get("dose_index", ""))
    except ValueError:
        return jsonify({"ok": False}), 400
    if not 1 <= dose_index <= tracking.MAX_DOSES_PER_DAY:
        return jsonify({"ok": False}), 400
    tracking.set_dose(medication_id, day, dose_index, request.form.get("taken") == "1")
    return jsonify({"ok": True})

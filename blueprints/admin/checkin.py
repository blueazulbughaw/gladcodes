"""Private daily check-in, one page per section (SECTIONS): Prayers &
devotion (/gc-admin/prayer), My emotions (/emotions), Body & food (/body),
Medicines (/medicine) and Learnings (/learnings). All autosave (no Save
button) and save only their own columns. Sleep and Instagram time are shown
but never typed; the phone sends them (personal.py /track/*). The overview
and "Today" strip live on My dashboard (personal.py), where login lands.

Never exposed publicly — nothing here is read by blueprints/public.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pymysql
from flask import current_app, jsonify, redirect, render_template, request, url_for

from database.db import execute, query, query_one, utc_now
from services import devotion, tracking
from services.content import render_markdown

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

_TEXT_FIELDS = (
    "mood_reason", "reading", "learnings", "bible_passage", "grateful", "win", "notes", "morning_prayer_note",
    "night_prayer_note", "devotion_thoughts", "food_breakfast", "food_lunch", "food_dinner", "food_snacks",
)

# Form -> column value for each check-in column.
FIELD_VALUES = {
    "mood": lambda: _scale("mood"),
    "energy": lambda: _scale("energy"),
    # No checkboxes for prayers: writing a prayer is what counts.
    "morning_prayer": lambda: 1 if _text("morning_prayer_note") else 0,
    "night_prayer": lambda: 1 if _text("night_prayer_note") else 0,
    "exercised": lambda: _flag("exercised"),
    "period_day": lambda: _flag("period_day"),
    "water_glasses": lambda: _water(),
}
FIELD_VALUES.update({name: (lambda name=name: _text(name)) for name in _TEXT_FIELDS})

# The daily inputs, one page each (sidebar groups: Prayer & devotion, Mental
# wellbeing, Health & fitness, Growth). Each page saves ONLY its own
# columns, so autosaving one page can never blank another page's boxes.
SECTIONS = {
    "prayer": {"title": "Prayers & devotion", "icon": "book-heart", "endpoint": "admin.checkin_prayer",
               "fields": ("morning_prayer_note", "morning_prayer", "bible_passage", "devotion_thoughts",
                          "night_prayer_note", "night_prayer")},
    "emotions": {"title": "My emotions", "icon": "heart", "endpoint": "admin.checkin_emotions",
                 "fields": ("mood", "mood_reason", "energy", "grateful")},
    "body": {"title": "Body & food", "icon": "heart-pulse", "endpoint": "admin.checkin_body",
             "fields": ("water_glasses", "exercised", "period_day",
                        "food_breakfast", "food_lunch", "food_dinner", "food_snacks")},
    "medicine": {"title": "Medicines", "icon": "pill", "endpoint": "admin.checkin_medicine",
                 "fields": ()},  # doses save one checkbox at a time (/today/dose)
    "learnings": {"title": "Learnings", "icon": "graduation-cap", "endpoint": "admin.checkin_learnings",
                  "fields": ("reading", "learnings", "win", "notes")},
}
SECTION_ENDPOINTS = {s["endpoint"] for s in SECTIONS.values()}


# Boxes Claude Duet can also fill (services/devotion.py), each with the
# columns that follow it. The page sends what each box held when it loaded
# (loaded_<name>); autosave only writes the box if you changed it, so a
# page left open can't blank out a prayer Duet saved meanwhile.
DUET_BOXES = {
    "morning_prayer_note": ("morning_prayer_note", "morning_prayer"),
    "night_prayer_note": ("night_prayer_note", "night_prayer"),
    "bible_passage": ("bible_passage",),
}


def _box_changed(name) -> bool:
    loaded = request.form.get(f"loaded_{name}")
    if loaded is None:  # a page from before this guard: old behaviour
        return True
    return request.form.get(name, "").strip() != loaded.strip()


def save_checkin(day: date, fields) -> None:
    """Upsert the given columns (one section's) from the posted form."""
    fields = tuple(f for f in fields if f in FIELD_VALUES)
    if not fields:
        return
    guard = {column: box for box, cols in DUET_BOXES.items() for column in cols}
    updates, update_params = [], []
    for c in fields + ("updated_at",):
        if c in guard:
            updates.append(f"{c} = IF(%s, VALUES({c}), {c})")
            update_params.append(_box_changed(guard[c]))
        else:
            updates.append(f"{c} = VALUES({c})")
    # Column names come from the fixed FIELD_VALUES/SECTIONS tables, never input.
    execute(
        f"""
        INSERT INTO daily_checkins (checkin_date, {", ".join(fields)}, updated_at)
        VALUES ({", ".join(["%s"] * (len(fields) + 2))})
        ON DUPLICATE KEY UPDATE {", ".join(updates)}
        """,
        (day, *(FIELD_VALUES[f]() for f in fields), utc_now(), *update_params),
    )


def devotion_view(entry):
    """The devotion Duet saved for this day, ready to show read-only in the
    Devotion card: infographic data + the written devotion as sanitized HTML."""
    entry = entry or {}
    markdown_text = entry.get("devotion_markdown")
    infographics = devotion.load_infographics(entry.get("devotion_infographic"))
    if not markdown_text and not infographics:
        return None
    return {
        "title": devotion.devotion_title(markdown_text, infographics),
        "infographics": infographics,
        "html": render_markdown(markdown_text) if markdown_text else "",
    }


def _wants_json() -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def medications_for(day: date):
    """Medicines due that day, each with its dose checkboxes (taken or not)."""
    taken = tracking.doses_taken(day, day)
    return [
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


@admin_bp.route("/today", methods=["GET", "POST"])
def today():
    """The old single check-in page. Everything moved to the section pages
    and My dashboard; this stays so the installed app's id, old bookmarks
    and reminder taps still land somewhere sensible."""
    day = request.args.get("date")
    return redirect(url_for("admin.personal_dashboard", d=day) if day else url_for("admin.personal_dashboard"))


def section_page(key):
    section = SECTIONS[key]
    endpoint = section["endpoint"]
    today_date = local_today()

    if request.method == "POST":
        # Autosave: the page posts its form in the background on every change
        # (no Save button). The <noscript> fallback does a normal post.
        save_timezone(request.form.get("tz"))
        day = parse_day(request.form.get("checkin_date"), today_date)
        save_checkin(day, section["fields"])
        if _wants_json():
            return jsonify({"ok": True})
        return redirect(url_for(endpoint) if day == today_date else url_for(endpoint, date=day.isoformat()))

    day = parse_day(request.args.get("date"), today_date)
    entry = query_one("SELECT * FROM daily_checkins WHERE checkin_date = %s", (day,))
    context = {}
    if key == "prayer":
        context["saved_devotion"] = devotion_view(entry)
    elif key == "emotions":
        context["moods"] = MOODS
    elif key == "medicine":
        context["medications"] = medications_for(day)
    elif key == "body":
        has_tracking = tracking.tracking_status()
        context.update(
            sleep_minutes=tracking.sleep_by_day([day]).get(day),
            app_minutes=tracking.app_minutes_by_day(tracking.TRACKED_APP, [day], local_tz_name()).get(day, 0),
            tracked_app=tracking.TRACKED_APP,
            tracking_connected=bool(has_tracking["last_sleep"] or has_tracking["last_app"]),
        )

    return render_template(
        "checkin_section.html",
        section_key=key,
        section=section,
        endpoint=endpoint,
        day=day,
        is_today=day == today_date,
        # Day navigation: edit any past day (forgot something yesterday?).
        prev_day=day - timedelta(days=1),
        next_day=day + timedelta(days=1) if day < today_date else None,
        today_date=today_date,
        entry=entry,
        **context,
    )


@admin_bp.route("/prayer", methods=["GET", "POST"])
def checkin_prayer():
    return section_page("prayer")


@admin_bp.route("/emotions", methods=["GET", "POST"])
def checkin_emotions():
    return section_page("emotions")


@admin_bp.route("/body", methods=["GET", "POST"])
def checkin_body():
    return section_page("body")


@admin_bp.route("/medicine", methods=["GET", "POST"])
def checkin_medicine():
    return section_page("medicine")


@admin_bp.route("/learnings", methods=["GET", "POST"])
def checkin_learnings():
    return section_page("learnings")


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

"""Personal dashboard (/gc-admin/me): everything from the daily check-in
and the phone, kept separate from the website CMS dashboard (/gc-admin/).
Mood + reasons, prayers, medicines, sleep, Instagram time, period cycle,
and the logs (Bible passages, reading, gratitude, app ideas).

Also the phone-automation endpoints (/gc-admin/track/*), authenticated by a
bearer token instead of the JWT cookie, since an iPhone Shortcut / Android
automation has no browser session.
"""
from datetime import timedelta

from flask import abort, current_app, jsonify, redirect, render_template, request, url_for

from database.db import query
from services import tracking

from . import admin_bp
from .checkin import MOODS, checkin_streak, current_streak, local_today, local_tz_name, parse_day

CHART_DAYS = 30
LOG_LIMIT = 30


def _series(by_day, days, key):
    return [
        float(by_day[d][key]) if d in by_day and by_day[d][key] is not None else None
        for d in days
    ]


def medication_adherence(meds, taken, days):
    """Per medicine: 7 day cells (taken/expected doses, or None if not due)."""
    rows = []
    for med in meds:
        cells, expected_total, taken_total = [], 0, 0
        for day in days:
            if not tracking.medication_due(med, day) or med["frequency"] == "as_needed":
                cells.append({"day": day, "due": False, "taken": len(taken.get((med["id"], day), ())), "expected": 0})
                continue
            expected = tracking.dose_count(med)
            got = min(expected, len(taken.get((med["id"], day), ())))
            expected_total += expected
            taken_total += got
            cells.append({"day": day, "due": True, "taken": got, "expected": expected})
        pct = round(taken_total / expected_total * 100) if expected_total else None
        rows.append({"name": med["name"], "cells": cells, "pct": pct})
    return rows


@admin_bp.route("/me")
def personal_dashboard():
    today = local_today()
    tz_name = local_tz_name()
    days = [today - timedelta(days=i) for i in range(CHART_DAYS - 1, -1, -1)]
    week = days[-7:]

    rows = query("SELECT * FROM daily_checkins WHERE checkin_date >= %s ORDER BY checkin_date", (days[0],))
    by_day = {row["checkin_date"]: row for row in rows}

    sleep = tracking.sleep_by_day(days)
    app_minutes = tracking.app_minutes_by_day(tracking.TRACKED_APP, days[-14:], tz_name)

    prayer_days = [d for d, r in by_day.items() if r["morning_prayer"] and r["night_prayer"]]
    week_sleep = [sleep[d] for d in week if d in sleep]
    week_app = [app_minutes.get(d, 0) for d in week]

    meds = tracking.active_medications()
    adherence = medication_adherence(meds, tracking.doses_taken(week[0], week[-1]), week)
    med_pcts = [m["pct"] for m in adherence if m["pct"] is not None]

    period_days = [r["checkin_date"] for r in query("SELECT checkin_date FROM daily_checkins WHERE period_day = 1")]
    periods = tracking.periods_from_days(period_days)
    cycle = tracking.cycle_summary(periods, today)

    def log(column):
        # column comes from the fixed tuple below, never from input.
        return query(
            f"SELECT checkin_date, {column} AS text FROM daily_checkins WHERE {column} IS NOT NULL AND {column} <> '' "
            f"ORDER BY checkin_date DESC LIMIT {LOG_LIMIT}"
        )

    logs = [
        ("Bible passages", "book-heart", log("bible_passage")),
        ("Reading", "book-open", log("reading")),
        ("Thankful for", "heart", log("grateful")),
        ("App ideas", "lightbulb", log("app_ideas")),
    ]
    mood_reasons = query(
        "SELECT checkin_date, mood, mood_reason FROM daily_checkins WHERE mood IS NOT NULL "
        "ORDER BY checkin_date DESC LIMIT 14"
    )

    return render_template(
        "me.html",
        today=today,
        moods=MOODS,
        streak=checkin_streak(today),
        prayer_streak=current_streak(prayer_days, today),
        avg_sleep=round(sum(week_sleep) / len(week_sleep)) if week_sleep else None,
        avg_app=round(sum(week_app) / len(week_app)) if any(week_app) else None,
        med_pct=round(sum(med_pcts) / len(med_pcts)) if med_pcts else None,
        tracked_app=tracking.TRACKED_APP,
        chart={
            "labels": [d.strftime("%b %d") for d in days],
            "mood": _series(by_day, days, "mood"),
            "energy": _series(by_day, days, "energy"),
            "sleep_labels": [d.strftime("%b %d") for d in days[-14:]],
            "sleep": [round(sleep[d] / 60, 1) if d in sleep else None for d in days[-14:]],
            "app": [app_minutes.get(d, 0) for d in days[-14:]],
        },
        adherence=adherence,
        periods=list(reversed(periods))[:6],
        cycle=cycle,
        mood_reasons=mood_reasons,
        logs=logs,
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
    """{"hours": 7.25} or {"minutes": 435}, optional "date" (YYYY-MM-DD,
    defaults to today = the morning you woke up)."""
    _require_token()
    data = _payload()
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

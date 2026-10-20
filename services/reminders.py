"""Check-in reminder schedule, driven by GET /gc-admin/reminders/tick.

A cron job (installed by .cpanel.yml on deploy) pings that URL every 15
minutes. It runs inside the Passenger app on purpose: env vars set in the
cPanel Python App panel (DB password etc.) only exist there, not in a cron
shell. Each tick sends at most the one reminder that's due, and
claim_reminder() makes sure it goes out once even though the tick repeats
within the hour (and even if a stranger pings the URL).
"""
from database.db import transaction


def evening_done(entry) -> bool:
    return bool(entry and (entry["night_prayer"] or entry["win"] or entry["mood"]))


def due_reminder(hour, morning_hour, evening_hour, entry):
    if hour == morning_hour and entry is None:
        return "morning"
    if hour == evening_hour and not evening_done(entry):
        return "evening"
    return None


def reminder_text(kind, entry):
    if kind == "morning":
        return "Good morning ☀️", "Start with your morning prayer, then your medicine and a glass of water, before Instagram."
    if entry and entry["bible_passage"]:
        return "Night prayer time 🌙", "Close the day: how you felt and why, what you're thankful for, and your win."
    return "Night prayer time 🌙", "Close the day: how you felt, what you're thankful for, and today's Bible passage."


def claim_reminder(marker: str) -> bool:
    """Atomically record that `marker` (e.g. "2026-10-16:morning") is being
    sent. False if some earlier tick already sent it."""
    with transaction() as cursor:
        cursor.execute(
            """
            UPDATE checkin_app_state SET reminder_last_sent = %s
            WHERE id = 1 AND (reminder_last_sent IS NULL OR reminder_last_sent <> %s)
            """,
            (marker, marker),
        )
        return cursor.rowcount == 1

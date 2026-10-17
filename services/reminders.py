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
    return bool(entry and (entry["win"] or entry["focus"] or entry["priority_done"] or entry["scroll_minutes"] is not None))


def due_reminder(hour, morning_hour, evening_hour, entry):
    if hour == morning_hour and entry is None:
        return "morning"
    if hour == evening_hour and not evening_done(entry):
        return "evening"
    return None


def reminder_text(kind, entry):
    if kind == "morning":
        return "Good morning ☀️", "Check in before you open Instagram: mood, what you read, what you're thankful for."
    if entry and entry["top_priority"]:
        return "How did today go? 🌙", f"Did you ship “{entry['top_priority']}”? Log your win and focus."
    return "How did today go? 🌙", "Two minutes: your win, your focus, and how long you scrolled."


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

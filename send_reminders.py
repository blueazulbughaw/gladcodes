"""Check-in reminders over Web Push. Run hourly from cPanel cron:

    0 * * * * cd ~/gladcodes_app && ~/virtualenv/gladcodes_app/3.11/bin/python send_reminders.py

Each run checks the hour in LOCAL_TIMEZONE and pushes at most one reminder:
  - CHECKIN_MORNING_HOUR: only if today's check-in doesn't exist yet
  - CHECKIN_EVENING_HOUR: only if the evening half (win/focus/shipped/scroll) is empty
Any other hour, or when it's already done, it exits quietly.

Test it right now with:  python send_reminders.py --force morning
"""
import argparse

from flask import url_for

from app import create_app
from blueprints.admin.checkin import evening_done, local_now
from database.db import query_one
from services.push import enabled, send_to_all


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


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", choices=["morning", "evening"], help="send this reminder now, ignoring the hour")
    args = parser.parse_args()

    app = create_app()
    # A request context so url_for() works outside a real request.
    with app.test_request_context(base_url=app.config["PUBLIC_SITE_URL"]):
        if not enabled():
            print("VAPID keys not set; nothing to send.")
            return
        now = local_now()
        entry = query_one("SELECT * FROM daily_checkins WHERE checkin_date = %s", (now.date(),))
        kind = args.force or due_reminder(
            now.hour, app.config["CHECKIN_MORNING_HOUR"], app.config["CHECKIN_EVENING_HOUR"], entry
        )
        if not kind:
            return
        title, body = reminder_text(kind, entry)
        sent = send_to_all(title, body, url_for("admin.today"), tag=f"checkin-{kind}")
        print(f"{kind} reminder sent to {sent} device(s).")


if __name__ == "__main__":
    main()

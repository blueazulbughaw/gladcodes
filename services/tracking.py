"""Personal tracking for the private check-in + personal dashboard: periods,
medicine schedules, and data the phone sends automatically (sleep, app
time). Pure helpers first (unit-tested), DB helpers after. Nothing here is
ever read by blueprints/public.
"""
import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from database.db import execute, query, query_one, utc_now

MAX_DOSES_PER_DAY = 8
# The app whose open/close events the phone reports — the one to scroll less.
TRACKED_APP = "Instagram"
# A session whose "closed" event never arrived counts for at most this long.
DANGLING_SESSION_CAP = timedelta(minutes=15)
OPEN_SESSION_CAP = timedelta(hours=4)


# --- pure helpers ---------------------------------------------------------

def periods_from_days(days, gap_days: int = 1):
    """Group period-day dates into [(start, end)] runs, oldest first.

    A single unticked day inside a run (gap_days) is bridged, so forgetting
    to tick one day doesn't split one period into two.
    """
    periods = []
    for day in sorted(set(days)):
        if periods and (day - periods[-1][1]).days <= gap_days + 1:
            periods[-1][1] = day
        else:
            periods.append([day, day])
    return [(start, end) for start, end in periods]


def cycle_summary(periods, today):
    """Average cycle length (start to start, last 6 cycles) and the predicted
    next start. None values until there are two periods to compare."""
    starts = [start for start, _ in periods]
    gaps = [(b - a).days for a, b in zip(starts, starts[1:])][-6:]
    if not gaps:
        return {"average_cycle": None, "next_start": None, "days_until": None}
    average = round(sum(gaps) / len(gaps))
    next_start = starts[-1] + timedelta(days=average)
    return {"average_cycle": average, "next_start": next_start, "days_until": (next_start - today).days}


def medication_due(med, day) -> bool:
    start = med.get("start_date") or day
    if day < start:
        return False
    if med["frequency"] == "every_other_day":
        return (day - start).days % 2 == 0
    if med["frequency"] == "weekly":
        return day.weekday() == start.weekday()
    return True  # daily, as_needed


def dose_count(med) -> int:
    try:
        return max(1, min(MAX_DOSES_PER_DAY, int(med["doses_per_day"])))
    except (TypeError, ValueError):
        return 1


def session_minutes(sessions, start_utc, end_utc, now_utc) -> int:
    """Total minutes of sessions overlapping [start_utc, end_utc)."""
    total = timedelta()
    for s in sessions:
        opened = s["opened_at"]
        closed = s["closed_at"] or min(now_utc, opened + OPEN_SESSION_CAP)
        overlap = min(closed, end_utc) - max(opened, start_utc)
        if overlap > timedelta():
            total += overlap
    return round(total.total_seconds() / 60)


def local_day_bounds_utc(day, tz_name):
    """Naive-UTC [start, end) of a local calendar day, to match DATETIME columns."""
    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    to_utc = lambda dt: dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)  # noqa: E731
    return to_utc(start), to_utc(end)


# --- phone ingest token ---------------------------------------------------

def ensure_ingest_token() -> None:
    """Create the phone-automation token on first start (race-safe, same
    pattern as push.ensure_vapid_keys)."""
    execute(
        "UPDATE checkin_app_state SET ingest_token = %s WHERE id = 1 AND ingest_token IS NULL",
        (secrets.token_urlsafe(32),),
    )


def ingest_token():
    row = query_one("SELECT ingest_token FROM checkin_app_state WHERE id = 1")
    return row["ingest_token"] if row else None


def regenerate_ingest_token() -> None:
    execute("UPDATE checkin_app_state SET ingest_token = %s WHERE id = 1", (secrets.token_urlsafe(32),))


def token_matches(presented) -> bool:
    expected = ingest_token()
    return bool(expected and presented) and secrets.compare_digest(expected, presented)


# --- writes from the phone -----------------------------------------------

def record_sleep(day, minutes: int) -> None:
    execute(
        """
        INSERT INTO sleep_logs (sleep_date, minutes, updated_at) VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE minutes = VALUES(minutes), updated_at = VALUES(updated_at)
        """,
        (day, minutes, utc_now()),
    )


MIN_SLEEP = timedelta(hours=1)    # shorter = a nap or a mode flick, ignored
MAX_SLEEP = timedelta(hours=16)   # longer = a missed "end", ignored


def sleep_minutes_between(started, ended):
    """Minutes asleep between a Sleep-mode start and end, or None if the gap
    doesn't look like a night's sleep."""
    if not started or ended <= started:
        return None
    gap = ended - started
    if not MIN_SLEEP <= gap <= MAX_SLEEP:
        return None
    return round(gap.total_seconds() / 60)


def record_sleep_event(event: str, wake_day) -> int:
    """'start' (Sleep mode on) remembers the time; 'end' (Sleep mode off)
    saves the minutes in between for `wake_day`. Returns minutes saved
    (0 when nothing was saved)."""
    now = utc_now()
    if event == "start":
        execute("UPDATE checkin_app_state SET sleep_started_at = %s WHERE id = 1", (now,))
        return 0
    row = query_one("SELECT sleep_started_at FROM checkin_app_state WHERE id = 1")
    minutes = sleep_minutes_between(row["sleep_started_at"] if row else None, now)
    execute("UPDATE checkin_app_state SET sleep_started_at = NULL WHERE id = 1")
    if minutes:
        record_sleep(wake_day, minutes)
    return minutes or 0


def record_app_event(app: str, event: str) -> None:
    now = utc_now()
    if event == "opened":
        # A previous session that never got its "closed" event: cap it.
        execute(
            """
            UPDATE app_sessions SET closed_at = LEAST(opened_at + INTERVAL 15 MINUTE, %s)
            WHERE app = %s AND closed_at IS NULL
            """,
            (now, app),
        )
        execute("INSERT INTO app_sessions (app, opened_at) VALUES (%s, %s)", (app, now))
    elif event == "closed":
        execute(
            """
            UPDATE app_sessions SET closed_at = %s
            WHERE app = %s AND closed_at IS NULL AND opened_at >= %s
            ORDER BY opened_at DESC LIMIT 1
            """,
            (now, app, now - OPEN_SESSION_CAP),
        )


# --- reads for the Today page / personal dashboard -----------------------

def app_minutes_by_day(app: str, days, tz_name):
    """{day: minutes} for each local day in `days`."""
    if not days:
        return {}
    first, _ = local_day_bounds_utc(min(days), tz_name)
    _, last = local_day_bounds_utc(max(days), tz_name)
    sessions = query(
        "SELECT opened_at, closed_at FROM app_sessions WHERE app = %s AND opened_at < %s AND (closed_at IS NULL OR closed_at > %s)",
        (app, last, first - OPEN_SESSION_CAP),
    )
    now = utc_now()
    result = {}
    for day in days:
        start, end = local_day_bounds_utc(day, tz_name)
        result[day] = session_minutes(sessions, start, end, now)
    return result


def sleep_by_day(days):
    if not days:
        return {}
    rows = query(
        "SELECT sleep_date, minutes FROM sleep_logs WHERE sleep_date BETWEEN %s AND %s",
        (min(days), max(days)),
    )
    return {row["sleep_date"]: row["minutes"] for row in rows}


def active_medications():
    return query("SELECT * FROM medications WHERE is_active = 1 ORDER BY sort_order, id")


def doses_taken(start, end):
    """{(medication_id, date): {dose_index, ...}} for dates in [start, end]."""
    rows = query(
        "SELECT medication_id, dose_date, dose_index FROM medication_doses WHERE dose_date BETWEEN %s AND %s",
        (start, end),
    )
    taken = {}
    for row in rows:
        taken.setdefault((row["medication_id"], row["dose_date"]), set()).add(row["dose_index"])
    return taken


def set_dose(medication_id: int, day, dose_index: int, taken: bool) -> None:
    if taken:
        execute(
            "INSERT IGNORE INTO medication_doses (medication_id, dose_date, dose_index, taken_at) VALUES (%s, %s, %s, %s)",
            (medication_id, day, dose_index, utc_now()),
        )
    else:
        execute(
            "DELETE FROM medication_doses WHERE medication_id = %s AND dose_date = %s AND dose_index = %s",
            (medication_id, day, dose_index),
        )


def tracking_status():
    last_sleep = query_one("SELECT sleep_date, minutes, updated_at FROM sleep_logs ORDER BY updated_at DESC LIMIT 1")
    last_app = query_one("SELECT app, opened_at, closed_at FROM app_sessions ORDER BY opened_at DESC LIMIT 1")
    return {"last_sleep": last_sleep, "last_app": last_app}


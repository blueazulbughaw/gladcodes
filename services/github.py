"""GitHub API client, cached. Never let a GitHub failure break a page —
callers must treat a None return as "hide this section".
"""
import json
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app

from database.db import execute, query_one

GITHUB_API_BASE = "https://api.github.com"


def _headers() -> dict:
    token = current_app.config.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_cached(cache_key: str):
    row = query_one(
        "SELECT payload, fetched_at FROM github_cache WHERE cache_key = %s",
        (cache_key,),
    )
    if not row:
        return None
    ttl = current_app.config["GITHUB_CACHE_TTL_SECONDS"]
    if datetime.now(timezone.utc) - row["fetched_at"].replace(tzinfo=timezone.utc) > timedelta(seconds=ttl):
        return None
    return json.loads(row["payload"])


def set_cached(cache_key: str, payload) -> None:
    # UTC_TIMESTAMP(), not NOW(): NOW() returns the DB server's local time,
    # and get_cached() below compares fetched_at against datetime.now(utc).
    # If the server isn't configured for UTC, that mismatch makes the TTL
    # check wrong in either direction (cache never hits, or serves stale
    # data far past 1 hour).
    execute(
        """
        INSERT INTO github_cache (cache_key, payload, fetched_at)
        VALUES (%s, %s, UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE payload = VALUES(payload), fetched_at = VALUES(fetched_at)
        """,
        (cache_key, json.dumps(payload)),
    )


def get_profile_summary(username: str):
    """Return {"profile": {...}, "repos": [...]} or None on any failure.

    Repos are the 6 most recently pushed-to, non-fork repos. Cached (github_cache,
    1 hour TTL) so a page render never blocks on the GitHub API.
    """
    if not username:
        return None

    cache_key = f"profile:{username}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        profile_resp = requests.get(f"{GITHUB_API_BASE}/users/{username}", headers=_headers(), timeout=5)
        repos_resp = requests.get(
            f"{GITHUB_API_BASE}/users/{username}/repos",
            headers=_headers(),
            params={"sort": "pushed", "per_page": 10},
            timeout=5,
        )
        profile_resp.raise_for_status()
        repos_resp.raise_for_status()
        profile_json = profile_resp.json()
        repos_json = [r for r in repos_resp.json() if not r.get("fork")][:6]
    except requests.RequestException:
        return None

    payload = {
        "profile": {
            "login": profile_json.get("login"),
            "avatar_url": profile_json.get("avatar_url"),
            "html_url": profile_json.get("html_url"),
            "public_repos": profile_json.get("public_repos"),
            "followers": profile_json.get("followers"),
        },
        "repos": [
            {
                "name": repo.get("name"),
                "html_url": repo.get("html_url"),
                "description": repo.get("description"),
                "stargazers_count": repo.get("stargazers_count", 0),
                "language": repo.get("language"),
                "pushed_at": repo.get("pushed_at"),
            }
            for repo in repos_json
        ],
    }

    set_cached(cache_key, payload)
    return payload


def normalize_username(value):
    """github_username is meant to be a bare username, but admins sometimes
    paste the full profile URL instead — accept both so a data-entry slip
    doesn't break the profile link or the GitHub API call."""
    if not value:
        return None
    value = value.strip().rstrip("/")
    if value.startswith("http://") or value.startswith("https://"):
        value = value.rsplit("/", 1)[-1]
    return value or None


def configured_username():
    row = query_one("SELECT setting_value FROM site_settings WHERE setting_key = 'github_username'")
    return normalize_username(row["setting_value"] if row else None)


def bucket_pushes_by_week(events, today, weeks: int = 12) -> dict:
    """Group PushEvents into Monday-start weeks ending with the current week.

    Pure function (no I/O) so it's testable. Counts pushes, not commits:
    GitHub stopped including commit counts in PushEvent payloads in 2025.
    """
    current_monday = today - timedelta(days=today.weekday())
    mondays = [current_monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    counts = {monday: 0 for monday in mondays}
    last_push = None
    pushes_30d = 0
    for event in events:
        if event.get("type") != "PushEvent" or not event.get("created_at"):
            continue
        created = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
        day = created.date()
        monday = day - timedelta(days=day.weekday())
        if monday in counts:
            counts[monday] += 1
        if (today - day).days < 30:
            pushes_30d += 1
        if last_push is None or event["created_at"] > last_push["pushed_at"]:
            last_push = {
                "repo": (event.get("repo") or {}).get("name", ""),
                "pushed_at": event["created_at"],
            }
    return {
        "labels": [monday.strftime("%b %d") for monday in mondays],
        "data": [counts[monday] for monday in mondays],
        "pushes_30d": pushes_30d,
        "last_push": last_push,
    }


def get_weekly_activity(username: str, weeks: int = 12):
    """Return {"labels", "data", "pushes_30d", "last_push"} for the public
    dashboard, or None on any failure (caller hides the section).

    Built from the public events feed, which covers ~90 days / 300 events —
    enough for 12 weeks. Cached like everything else here, so the dashboard
    picks up new pushes within an hour without ever blocking on GitHub.
    """
    if not username:
        return None

    cache_key = f"activity:{username}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    events = []
    try:
        for page in (1, 2, 3):
            resp = requests.get(
                f"{GITHUB_API_BASE}/users/{username}/events/public",
                headers=_headers(),
                params={"per_page": 100, "page": page},
                timeout=5,
            )
            resp.raise_for_status()
            batch = resp.json()
            events.extend(batch)
            if len(batch) < 100:
                break
    except (requests.RequestException, ValueError):
        return None

    payload = bucket_pushes_by_week(events, datetime.now(timezone.utc).date(), weeks)
    set_cached(cache_key, payload)
    return payload

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

"""GitHub API client, cached (Phase 1 step 5 wires this into the home page).

Kept as a minimal, honest stub for now: the function signature and cache
table (github_cache) are final, but the real fetch/cache logic lands when
the home page GitHub section is built. Never let a GitHub failure break a
page — callers must treat a None/[] return as "hide this section".
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
    execute(
        """
        INSERT INTO github_cache (cache_key, payload, fetched_at)
        VALUES (%s, %s, NOW())
        ON DUPLICATE KEY UPDATE payload = VALUES(payload), fetched_at = VALUES(fetched_at)
        """,
        (cache_key, json.dumps(payload)),
    )


def get_profile_summary(username: str):
    """Return {repos: [...], profile: {...}} or None on any failure."""
    cache_key = f"profile:{username}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        profile_resp = requests.get(f"{GITHUB_API_BASE}/users/{username}", headers=_headers(), timeout=5)
        repos_resp = requests.get(
            f"{GITHUB_API_BASE}/users/{username}/repos",
            headers=_headers(),
            params={"sort": "updated", "per_page": 6},
            timeout=5,
        )
        profile_resp.raise_for_status()
        repos_resp.raise_for_status()
        payload = {"profile": profile_resp.json(), "repos": repos_resp.json()}
    except requests.RequestException:
        return None

    set_cached(cache_key, payload)
    return payload

"""Prayers and devotions saved from Claude Duet (via the connector), plus
Bible progress. This is the ONLY data the connector can touch: the morning
and evening prayer, and the Devotion section of a day (Bible passage, the
written devotion, its infographic). Medicine, Body, Food, Learnings and
Emotions are never read or written here, and nothing here deletes a day.

Private like everything under /gc-admin: nothing in blueprints/public reads
these columns. Never log prayer or devotion text.
"""
import json
from datetime import date

from database.db import query, query_one, transaction, utc_now
from services import bible

PARTS = {"morning": ("morning_prayer_note", "morning_prayer"),
         "evening": ("night_prayer_note", "night_prayer")}
IF_EXISTS = ("ask", "replace", "add")

# TEXT holds 65,535 bytes; MEDIUMTEXT 16 MB. Checked in bytes (utf8mb4).
MAX_PRAYER_BYTES = 60_000
MAX_DEVOTION_BYTES = 2_000_000


class DevotionError(ValueError):
    """Bad input from the connector; the message is safe to show Claude."""


# --- infographic -------------------------------------------------------------
# Stored as data, not HTML: glad.codes draws it in its own style, so no
# outside markup ever runs in the private area. Shape (all text):
#   {"title", "subtitle", "key_verse": {"text", "ref"},
#    "cards": [{"label", "title", "passage", "summary", "quote", "quote_ref"}],
#    "tiles_heading", "tiles": [{"title", "text", "ref"}],
#    "closing_verse": {"text", "ref"}, "translation"}

_LIMITS = {"short": 200, "long": 2000}
_CARD_FIELDS = {"label": "short", "title": "short", "passage": "short",
                "summary": "long", "quote": "long", "quote_ref": "short"}
_TILE_FIELDS = {"title": "short", "text": "long", "ref": "short"}
_VERSE_FIELDS = {"text": "long", "ref": "short"}


def _text(value, kind, where):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DevotionError(f"{where} must be text")
    if len(value) > _LIMITS[kind]:
        raise DevotionError(f"{where} is too long (max {_LIMITS[kind]} characters)")
    return value.strip()


def _obj(value, fields, where):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DevotionError(f"{where} must be an object")
    out = {key: _text(value.get(key), kind, f"{where}.{key}") for key, kind in fields.items()}
    return out if any(out.values()) else None


def _list(value, fields, where, max_items):
    if value is None:
        return []
    if not isinstance(value, list):
        raise DevotionError(f"{where} must be a list")
    if len(value) > max_items:
        raise DevotionError(f"{where} can have at most {max_items} items")
    items = [_obj(item, fields, f"{where}[{i}]") for i, item in enumerate(value)]
    return [item for item in items if item]


def clean_infographic(data):
    """Validate the infographic and keep only known fields. None if absent."""
    if data in (None, "", {}):
        return None
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            raise DevotionError("infographic must be an object (or JSON text of one)") from None
    if not isinstance(data, dict):
        raise DevotionError("infographic must be an object")
    out = {
        "title": _text(data.get("title"), "short", "infographic.title"),
        "subtitle": _text(data.get("subtitle"), "long", "infographic.subtitle"),
        "key_verse": _obj(data.get("key_verse"), _VERSE_FIELDS, "infographic.key_verse"),
        "cards": _list(data.get("cards"), _CARD_FIELDS, "infographic.cards", 12),
        "tiles_heading": _text(data.get("tiles_heading"), "short", "infographic.tiles_heading"),
        "tiles": _list(data.get("tiles"), _TILE_FIELDS, "infographic.tiles", 8),
        "closing_verse": _obj(data.get("closing_verse"), _VERSE_FIELDS, "infographic.closing_verse"),
        "translation": _text(data.get("translation"), "short", "infographic.translation"),
    }
    if not out["title"]:
        raise DevotionError("infographic.title is required")
    return out


def load_infographics(raw):
    """Stored column → list of infographics (a day can hold more than one
    when a second devotion was added instead of replacing)."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    return data if isinstance(data, list) else [data]


def devotion_title(markdown_text, infographics):
    for graphic in infographics:
        if graphic.get("title"):
            return graphic["title"]
    for line in (markdown_text or "").splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            return title.split(":", 1)[1].strip() if title.lower().startswith("today's devotion:") else title
    return "Today's devotion"


# --- saving ------------------------------------------------------------------

def _check_if_exists(value):
    if value not in IF_EXISTS:
        raise DevotionError("if_exists must be ask, replace or add")
    return value


def _locked_row(cursor, day):
    """The day's devotional columns, row-locked for this save. Creates the
    day if it doesn't exist (an empty check-in row, like opening Today)."""
    cursor.execute(
        "INSERT INTO daily_checkins (checkin_date, updated_at) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE checkin_date = checkin_date",
        (day, utc_now()),
    )
    cursor.execute(
        "SELECT morning_prayer_note, night_prayer_note, bible_passage, devotion_markdown, "
        "devotion_infographic FROM daily_checkins WHERE checkin_date = %s FOR UPDATE",
        (day,),
    )
    return cursor.fetchone()


def save_prayer(day: date, part: str, text: str, if_exists: str = "ask") -> dict:
    """Save a prayer word for word into Morning or Evening → My prayer.
    The text is stored exactly as sent (no trimming, no cleanup). If the box
    already has a prayer and if_exists is "ask", nothing changes and the
    caller is told to ask Glad: replace, or add below."""
    if part not in PARTS:
        raise DevotionError("part must be morning or evening")
    if not isinstance(text, str) or not text.strip():
        raise DevotionError("prayer text is empty")
    if_exists = _check_if_exists(if_exists)
    column, flag = PARTS[part]  # fixed names from PARTS, never input

    with transaction() as cursor:
        row = _locked_row(cursor, day)
        existing = row[column] or ""
        if existing.strip() and if_exists == "ask":
            return {"saved": False, "needs_choice": True, "existing": existing}
        new_text = existing + "\n\n" + text if existing.strip() and if_exists == "add" else text
        if len(new_text.encode("utf-8")) > MAX_PRAYER_BYTES:
            raise DevotionError("prayer is too long")
        cursor.execute(
            f"UPDATE daily_checkins SET {column} = %s, {flag} = 1, updated_at = %s WHERE checkin_date = %s",
            (new_text, utc_now(), day),
        )
    return {"saved": True, "added": bool(existing.strip()) and if_exists == "add"}


def save_devotion(day: date, chapters: str, devotion_markdown: str, infographic=None,
                  if_exists: str = "ask") -> dict:
    """Fill the Devotion section: Bible passage (the chapters), the full
    written devotion and its infographic, and record the chapters for Bible
    progress. Never touches "Thoughts on the devotion"."""
    if not isinstance(devotion_markdown, str) or not devotion_markdown.strip():
        raise DevotionError("written devotion is empty")
    if len(devotion_markdown.encode("utf-8")) > MAX_DEVOTION_BYTES:
        raise DevotionError("written devotion is too long")
    parsed, problems = bible.parse_chapters(chapters if isinstance(chapters, str) else "")
    if problems:
        raise DevotionError("Couldn't read the chapters: " + "; ".join(problems))
    graphic = clean_infographic(infographic)
    if_exists = _check_if_exists(if_exists)
    passage = bible.format_chapters(parsed)

    with transaction() as cursor:
        row = _locked_row(cursor, day)
        has_devotion = bool(row["devotion_markdown"] or row["devotion_infographic"])
        has_passage = bool((row["bible_passage"] or "").strip())
        if (has_devotion or has_passage) and if_exists == "ask":
            return {"saved": False, "needs_choice": True,
                    "existing_passage": row["bible_passage"] or "",
                    "existing_title": devotion_title(row["devotion_markdown"], load_infographics(row["devotion_infographic"]))
                    if has_devotion else None}

        adding = if_exists == "add"
        graphics = load_infographics(row["devotion_infographic"]) if adding else []
        if graphic:
            graphics.append(graphic)
        markdown_text = devotion_markdown
        if adding and row["devotion_markdown"]:
            markdown_text = row["devotion_markdown"] + "\n\n---\n\n" + devotion_markdown
        if adding and has_passage:
            passage = row["bible_passage"].strip() + ", " + passage
        if len(markdown_text.encode("utf-8")) > MAX_DEVOTION_BYTES:
            raise DevotionError("written devotion is too long")

        cursor.execute(
            "UPDATE daily_checkins SET bible_passage = %s, devotion_markdown = %s, "
            "devotion_infographic = %s, updated_at = %s WHERE checkin_date = %s",
            (passage, markdown_text, json.dumps(graphics) if graphics else None, utc_now(), day),
        )
        if not adding:
            # Replacing this day's devotion (Glad chose replace): its chapters
            # are re-recorded from the new one. Other days are never touched.
            cursor.execute("DELETE FROM bible_chapters_read WHERE read_date = %s", (day,))
        for book, chapter in parsed:
            cursor.execute(
                "INSERT IGNORE INTO bible_chapters_read (read_date, book, chapter, created_at) "
                "VALUES (%s, %s, %s, %s)",
                (day, book, chapter, utc_now()),
            )
    return {"saved": True, "added": adding and (has_devotion or has_passage),
            "bible_passage": passage, "chapters": len(parsed)}


# --- reading -----------------------------------------------------------------

def get_day(day: date) -> dict:
    """Only the devotional part of a day: both prayers and the Devotion section."""
    row = query_one(
        "SELECT morning_prayer_note, night_prayer_note, bible_passage, devotion_thoughts, "
        "devotion_markdown, devotion_infographic FROM daily_checkins WHERE checkin_date = %s",
        (day,),
    ) or {}
    return {
        "date": day.isoformat(),
        "morning_prayer": row.get("morning_prayer_note") or "",
        "evening_prayer": row.get("night_prayer_note") or "",
        "devotion": {
            "bible_passage": row.get("bible_passage") or "",
            "written_devotion": row.get("devotion_markdown") or "",
            "infographics": load_infographics(row.get("devotion_infographic")),
            "my_thoughts": row.get("devotion_thoughts") or "",
        },
    }


def bible_progress() -> dict:
    """Distinct chapters covered by saved morning devotions, out of 1,189."""
    rows = query("SELECT DISTINCT book, chapter FROM bible_chapters_read")
    covered = sorted(
        ((r["book"], r["chapter"]) for r in rows if r["book"] in bible.CHAPTER_COUNT),
        key=lambda bc: (bible.BOOK_ORDER[bc[0]], bc[1]),
    )
    by_book = {}
    for book, chapter in covered:
        by_book.setdefault(book, []).append(chapter)
    return {
        "covered": len(covered),
        "total": bible.TOTAL_CHAPTERS,
        "percent": round(100 * len(covered) / bible.TOTAL_CHAPTERS, 1),
        "books_started": len(by_book),
        "books_finished": sum(1 for b, chs in by_book.items() if len(chs) == bible.CHAPTER_COUNT[b]),
        "by_book": by_book,
    }

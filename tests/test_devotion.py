"""Prayers + devotions saved by Claude Duet (services/devotion.py), the Bible
chapter parser, the Today page's read-only devotion view, and the autosave
guard that keeps an open Today page from blanking a Duet save."""
import json
import unittest
from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import patch

from app import create_app
from blueprints.admin.auth import COOKIE_NAME, issue_token
from blueprints.admin.checkin import SECTIONS
from blueprints.admin.csrf import CSRF_COOKIE_NAME
from services import bible, devotion

DAY = date(2026, 11, 13)
# A neutral stand-in for a written devotion (same shape as Duet's: title,
# sections, a table, a closing prayer).
SAMPLE_MARKDOWN = """# Today's Devotion: Waiting on God
**Friday, November 13, 2026**
*Read: Jeremiah 29, Psalm 37 (all quotations KJV)*

---

## 1. A letter to people stuck in a place they didn't choose (Jeremiah 29)

**What happened:** God told his people to *build houses, plant gardens* (vv. 5-6).

| While you wait for... | What the Bible says |
|---|---|
| **Direction** | Seek him with all your heart (Jer 29:13). |

## Prayer

*Father, I commit my way to you. Amen.*
"""

# The Nov 13 "Waiting on God" infographic, as the data Duet will send.
SAMPLE_INFOGRAPHIC = {
    "title": "Waiting on God",
    "subtitle": "For work, for provision, and for love. Seven chapters, one message.",
    "key_verse": {"text": "For I know the thoughts that I think toward you, saith the LORD…", "ref": "Jeremiah 29:11"},
    "cards": [
        {"label": "God has a plan in the waiting", "title": "Exiles get a letter", "passage": "Jeremiah 29",
         "summary": "God's people were carried off to Babylon.", "quote": "Ye shall seek me, and find me…",
         "quote_ref": "Jeremiah 29:13"},
        {"label": "Seek him first", "title": "Jesus on a hillside", "passage": "Matthew 6 & 7",
         "summary": "Jesus pointed at birds and wildflowers.", "quote": "Seek ye first the kingdom of God…",
         "quote_ref": "Matthew 6:33", "colour": "ignored"},
    ],
    "tiles_heading": "How to wait today",
    "tiles": [{"title": "Seek", "text": "Pray with your whole heart", "ref": "Jer 29:13"}],
    "closing_verse": {"text": "If God be for us, who can be against us?", "ref": "Romans 8:31"},
    "translation": "KJV",
}


class FakeCursor:
    """Stands in for a transaction() cursor: returns `row` for the locked
    SELECT and records every statement."""

    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.row

    def sql(self, start):
        return [c for c in self.calls if c[0].startswith(start)]


def fake_transaction(cursor):
    @contextmanager
    def _tx():
        yield cursor
    return _tx


EMPTY_ROW = {"morning_prayer_note": None, "night_prayer_note": None, "bible_passage": None,
             "devotion_markdown": None, "devotion_infographic": None}


class BibleParserTests(unittest.TestCase):
    def test_canon_has_1189_chapters(self):
        self.assertEqual(len(bible.BOOKS), 66)
        self.assertEqual(bible.TOTAL_CHAPTERS, 1189)

    def test_sample_reading_parses(self):
        found, problems = bible.parse_chapters("Jeremiah 29, Psalm 37, Proverbs 3, Romans 8, Psalm 51, Matthew 6 and 7")
        self.assertEqual(problems, [])
        self.assertEqual(found, [("Jeremiah", 29), ("Psalms", 37), ("Proverbs", 3), ("Romans", 8),
                                 ("Psalms", 51), ("Matthew", 6), ("Matthew", 7)])
        self.assertEqual(bible.format_chapters(found),
                         "Jeremiah 29, Psalm 37, Proverbs 3, Romans 8, Psalm 51, Matthew 6–7")

    def test_abbreviations_verses_and_ranges(self):
        cases = {
            "Rom 8:28-39": [("Romans", 8)],
            "Matt 6:25-7:5": [("Matthew", 6), ("Matthew", 7)],
            "1 Cor 13; II Kings 2": [("1 Corinthians", 13), ("2 Kings", 2)],
            "Song of Songs 2": [("Song of Solomon", 2)],
            "I John 4 & Jude 1": [("1 John", 4), ("Jude", 1)],
            "Phil 4, Philem 1, Judg 6": [("Philippians", 4), ("Philemon", 1), ("Judges", 6)],
            "Ps 23, 24-25": [("Psalms", 23), ("Psalms", 24), ("Psalms", 25)],
        }
        for text, expected in cases.items():
            self.assertEqual(bible.parse_chapters(text), (expected, []), text)

    def test_bad_references_are_reported_not_guessed(self):
        self.assertEqual(bible.parse_chapters("Psalm 151")[1], ["Psalms has no chapter 151"])
        self.assertEqual(bible.parse_chapters("Hezekiah 3")[1], ["Unknown book: Hezekiah"])
        self.assertEqual(bible.parse_chapters("")[1], ["No chapters found"])


class InfographicTests(unittest.TestCase):
    def test_keeps_known_fields_only(self):
        clean = devotion.clean_infographic(SAMPLE_INFOGRAPHIC)
        self.assertEqual(clean["title"], "Waiting on God")
        self.assertEqual(len(clean["cards"]), 2)
        self.assertNotIn("colour", clean["cards"][1])
        self.assertEqual(clean["tiles"][0]["title"], "Seek")

    def test_accepts_json_text(self):
        self.assertEqual(devotion.clean_infographic(json.dumps(SAMPLE_INFOGRAPHIC))["title"], "Waiting on God")

    def test_rejects_bad_shapes(self):
        for bad in ({"subtitle": "no title"}, {"title": "x", "cards": "nope"}, {"title": 5}, "not json", [1]):
            with self.assertRaises(devotion.DevotionError):
                devotion.clean_infographic(bad)
        with self.assertRaises(devotion.DevotionError):
            devotion.clean_infographic({"title": "x", "cards": [{}] * 13})

    def test_title_falls_back_to_markdown_heading(self):
        self.assertEqual(devotion.devotion_title("# Today's Devotion: Waiting on God\nbody", []), "Waiting on God")


class SavePrayerTests(unittest.TestCase):
    def run_save(self, row, *args, **kwargs):
        cursor = FakeCursor(row)
        with patch("services.devotion.transaction", fake_transaction(cursor)):
            return devotion.save_prayer(DAY, *args, **kwargs), cursor

    def test_saves_word_for_word(self):
        spoken = "  Lord, um, um, thank you po for this day. Salamat, Panginoon.\n"
        result, cursor = self.run_save(EMPTY_ROW, "morning", spoken)
        self.assertEqual(result, {"saved": True, "added": False})
        sql, params = cursor.sql("UPDATE")[0]
        self.assertIn("SET morning_prayer_note = %s, morning_prayer = 1", sql)
        self.assertEqual(params[0], spoken)  # not trimmed, not cleaned up
        self.assertEqual(params[2], DAY)

    def test_existing_prayer_asks_first_and_changes_nothing(self):
        row = dict(EMPTY_ROW, night_prayer_note="Earlier prayer")
        result, cursor = self.run_save(row, "evening", "New prayer")
        self.assertEqual(result, {"saved": False, "needs_choice": True, "existing": "Earlier prayer"})
        self.assertEqual(cursor.sql("UPDATE"), [])

    def test_add_and_replace(self):
        row = dict(EMPTY_ROW, night_prayer_note="Earlier prayer")
        result, cursor = self.run_save(row, "evening", "New prayer", if_exists="add")
        self.assertTrue(result["added"])
        self.assertEqual(cursor.sql("UPDATE")[0][1][0], "Earlier prayer\n\nNew prayer")
        _, cursor = self.run_save(row, "evening", "New prayer", if_exists="replace")
        self.assertIn("night_prayer_note = %s, night_prayer = 1", cursor.sql("UPDATE")[0][0])
        self.assertEqual(cursor.sql("UPDATE")[0][1][0], "New prayer")

    def test_rejects_bad_input(self):
        for args in (("noon", "x"), ("morning", "   "), ("morning", None)):
            with self.assertRaises(devotion.DevotionError):
                self.run_save(EMPTY_ROW, *args)
        with self.assertRaises(devotion.DevotionError):
            self.run_save(EMPTY_ROW, "morning", "x", if_exists="delete")

    def test_only_touches_prayer_columns(self):
        _, cursor = self.run_save(EMPTY_ROW, "morning", "Amen")
        for sql, _ in cursor.calls:
            for private in ("mood", "medication", "food_", "water", "learnings", "grateful", "exercised"):
                self.assertNotIn(private, sql)


class SaveDevotionTests(unittest.TestCase):
    def setUp(self):
        self.markdown = SAMPLE_MARKDOWN

    def run_save(self, row, **kwargs):
        cursor = FakeCursor(row)
        kwargs.setdefault("chapters", "Jeremiah 29, Psalm 37, Proverbs 3, Romans 8, Psalm 51, Matthew 6 and 7")
        kwargs.setdefault("devotion_markdown", self.markdown)
        kwargs.setdefault("infographic", SAMPLE_INFOGRAPHIC)
        with patch("services.devotion.transaction", fake_transaction(cursor)):
            return devotion.save_devotion(DAY, **kwargs), cursor

    def test_saves_whole_devotion_and_chapters(self):
        result, cursor = self.run_save(EMPTY_ROW)
        self.assertEqual(result["chapters"], 7)
        self.assertEqual(result["bible_passage"], "Jeremiah 29, Psalm 37, Proverbs 3, Romans 8, Psalm 51, Matthew 6–7")
        sql, params = cursor.sql("UPDATE")[0]
        self.assertNotIn("devotion_thoughts", sql)  # Glad's own box: never touched
        self.assertEqual(params[1], self.markdown)  # the whole thing, not a summary
        self.assertEqual(json.loads(params[2])[0]["title"], "Waiting on God")
        inserts = cursor.sql("INSERT IGNORE INTO bible_chapters_read")
        self.assertEqual([p[1:3] for _, p in inserts][-2:], [("Matthew", 6), ("Matthew", 7)])
        self.assertEqual(len(inserts), 7)

    def test_existing_devotion_asks_first(self):
        row = dict(EMPTY_ROW, bible_passage="Psalm 23")
        result, cursor = self.run_save(row)
        self.assertFalse(result["saved"])
        self.assertTrue(result["needs_choice"])
        self.assertEqual(result["existing_passage"], "Psalm 23")
        self.assertEqual(cursor.sql("UPDATE"), [])
        self.assertEqual(cursor.sql("INSERT IGNORE INTO bible_chapters_read"), [])

    def test_add_keeps_both(self):
        row = dict(EMPTY_ROW, bible_passage="Psalm 23", devotion_markdown="# First",
                   devotion_infographic=json.dumps([{"title": "First"}]))
        result, cursor = self.run_save(row, chapters="John 15", if_exists="add")
        params = cursor.sql("UPDATE")[0][1]
        self.assertEqual(params[0], "Psalm 23, John 15")
        self.assertTrue(params[1].startswith("# First\n\n---\n\n"))
        self.assertEqual([g["title"] for g in json.loads(params[2])], ["First", "Waiting on God"])
        self.assertEqual(cursor.sql("DELETE"), [])

    def test_replace_rerecords_only_that_days_chapters(self):
        row = dict(EMPTY_ROW, bible_passage="Psalm 23", devotion_markdown="# First")
        _, cursor = self.run_save(row, chapters="John 15", if_exists="replace")
        deletes = cursor.sql("DELETE")
        self.assertEqual(len(deletes), 1)
        self.assertIn("WHERE read_date = %s", deletes[0][0])
        self.assertEqual(deletes[0][1], (DAY,))

    def test_bad_chapters_save_nothing(self):
        with self.assertRaises(devotion.DevotionError) as err:
            self.run_save(EMPTY_ROW, chapters="Hezekiah 3")
        self.assertIn("Unknown book: Hezekiah", str(err.exception))

    def test_infographic_optional_devotion_required(self):
        result, _ = self.run_save(EMPTY_ROW, infographic=None)
        self.assertTrue(result["saved"])
        with self.assertRaises(devotion.DevotionError):
            self.run_save(EMPTY_ROW, devotion_markdown="  ")


class ReadTests(unittest.TestCase):
    @patch("services.devotion.query_one")
    def test_get_day_returns_only_devotional_fields(self, mock_query_one):
        mock_query_one.return_value = {
            "morning_prayer_note": "Morning", "night_prayer_note": None, "bible_passage": "Psalm 37",
            "devotion_thoughts": "Mine", "devotion_markdown": "# D",
            "devotion_infographic": json.dumps([{"title": "T"}]),
        }
        day = devotion.get_day(DAY)
        sql = mock_query_one.call_args[0][0]
        for private in ("mood", "food_", "water", "learnings", "grateful", "SELECT *"):
            self.assertNotIn(private, sql)
        self.assertEqual(day["morning_prayer"], "Morning")
        self.assertEqual(day["evening_prayer"], "")
        self.assertEqual(day["devotion"]["infographics"], [{"title": "T"}])
        self.assertEqual(set(day), {"date", "morning_prayer", "evening_prayer", "devotion"})

    @patch("services.devotion.query")
    def test_bible_progress(self, mock_query):
        mock_query.return_value = [{"book": "Matthew", "chapter": 7}, {"book": "Jude", "chapter": 1},
                                   {"book": "Matthew", "chapter": 6}, {"book": "Nonsense", "chapter": 1}]
        progress = devotion.bible_progress()
        self.assertEqual(progress["covered"], 3)
        self.assertEqual(progress["total"], 1189)
        self.assertEqual(progress["by_book"], {"Matthew": [6, 7], "Jude": [1]})
        self.assertEqual(progress["books_finished"], 1)  # Jude has one chapter


class TodayDevotionPageTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            token = issue_token("glad")
        self.client.set_cookie(COOKIE_NAME, token)
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")

    @patch("blueprints.admin.checkin.local_tz_name", return_value="America/New_York")
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 11, 13, 7, 30))
    @patch("blueprints.admin.checkin.tracking")
    @patch("blueprints.admin.checkin.query_one")
    @patch("blueprints.admin.checkin.query", return_value=[])
    def test_saved_devotion_shows_in_devotion_card(self, _q, mock_query_one, mock_tracking, *_):
        markdown_text = SAMPLE_MARKDOWN + "\n<script>alert(1)</script>"
        mock_query_one.return_value = {
            "morning_prayer_note": "Lord, um, salamat po", "night_prayer_note": None,
            "bible_passage": "Jeremiah 29, Psalm 37", "devotion_thoughts": "My own thoughts",
            "devotion_markdown": markdown_text,
            "devotion_infographic": json.dumps([devotion.clean_infographic(SAMPLE_INFOGRAPHIC)]),
            "water_glasses": 0, "mood": None, "energy": None,
        }
        mock_tracking.active_medications.return_value = []
        mock_tracking.sleep_by_day.return_value = {}
        mock_tracking.app_minutes_by_day.return_value = {}
        mock_tracking.tracking_status.return_value = {"last_sleep": None, "last_app": None}
        mock_tracking.TRACKED_APP = "Instagram"

        body = self.client.get("/gc-admin/prayer").get_data(as_text=True)
        card = body.split("Devotion</h2>")[1].split("</section>")[0]
        for text in ("Waiting on God", "Exiles get a letter", "Jeremiah 29:13", "How to wait today",
                     "Read the full devotion", "A letter to people stuck", "Romans 8:31 · KJV", "My own thoughts"):
            self.assertIn(text, card)
        self.assertNotIn("<script>alert(1)</script>", body)  # devotion Markdown goes through bleach
        self.assertLess(card.index("Waiting on God"), card.index("Thoughts on the devotion"))
        self.assertIn('name="loaded_morning_prayer_note" value="Lord, um, salamat po"', body)

    @patch("blueprints.admin.checkin.local_tz_name", return_value="America/New_York")
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 11, 13, 7, 30))
    @patch("blueprints.admin.checkin.tracking")
    @patch("blueprints.admin.checkin.query_one", return_value=None)
    @patch("blueprints.admin.checkin.query", return_value=[])
    def test_no_devotion_no_panel(self, _q, _qo, mock_tracking, *_):
        mock_tracking.active_medications.return_value = []
        mock_tracking.sleep_by_day.return_value = {}
        mock_tracking.app_minutes_by_day.return_value = {}
        mock_tracking.tracking_status.return_value = {"last_sleep": None, "last_app": None}
        body = self.client.get("/gc-admin/prayer").get_data(as_text=True)
        self.assertNotIn("Read the full devotion", body)


class AutosaveGuardTests(unittest.TestCase):
    """An open prayer page must not overwrite a prayer Duet saved after it loaded."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            token = issue_token("glad")
        self.client.set_cookie(COOKIE_NAME, token)
        self.client.set_cookie(CSRF_COOKIE_NAME, "test-csrf")

    def post(self, mock_execute, **fields):
        data = {"csrf_token": "test-csrf", "checkin_date": "2026-11-13", **fields}
        self.client.post("/gc-admin/prayer", headers={"X-Requested-With": "fetch"}, data=data)
        sql, params = mock_execute.call_args[0]
        update_flags = params[len(SECTIONS["prayer"]["fields"]) + 2:]
        return sql, update_flags

    @patch("blueprints.admin.checkin.saved_timezone", return_value=None)
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 11, 13, 9, 0))
    @patch("blueprints.admin.checkin.execute")
    def test_unchanged_boxes_keep_database_value(self, mock_execute, *_):
        sql, flags = self.post(mock_execute, morning_prayer_note="", loaded_morning_prayer_note="",
                               night_prayer_note="", loaded_night_prayer_note="",
                               bible_passage="", loaded_bible_passage="", devotion_thoughts="Mine", water=["1"])
        self.assertIn("morning_prayer_note = IF(%s, VALUES(morning_prayer_note), morning_prayer_note)", sql)
        self.assertIn("morning_prayer = IF(%s, VALUES(morning_prayer), morning_prayer)", sql)
        self.assertIn("devotion_thoughts = VALUES(devotion_thoughts)", sql)  # Glad's own box: always saved
        self.assertNotIn("water_glasses", sql)  # the prayer page never touches other sections
        self.assertNotIn("devotion_markdown", sql)
        self.assertEqual(flags, (False,) * 5)

    @patch("blueprints.admin.checkin.saved_timezone", return_value=None)
    @patch("blueprints.admin.checkin.local_now", return_value=datetime(2026, 11, 13, 9, 0))
    @patch("blueprints.admin.checkin.execute")
    def test_edited_box_is_saved(self, mock_execute, *_):
        _, flags = self.post(mock_execute, morning_prayer_note="Edited", loaded_morning_prayer_note="Duet's",
                             night_prayer_note="", loaded_night_prayer_note="",
                             bible_passage="Psalm 1", loaded_bible_passage="Psalm 1 ")
        # one flag per guarded column, in the prayer page's field order
        guarded = [c for c in SECTIONS["prayer"]["fields"] if c != "devotion_thoughts"]
        self.assertEqual(dict(zip(guarded, flags)), {
            "morning_prayer": True, "night_prayer": False, "bible_passage": False,
            "morning_prayer_note": True, "night_prayer_note": False,
        })


if __name__ == "__main__":
    unittest.main()

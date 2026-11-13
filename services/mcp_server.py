"""The MCP side of the Claude connector: JSON-RPC 2.0 over Streamable HTTP
(plain JSON responses, no SSE stream, no sessions), hand-written because
the official MCP SDK needs Python 3.10+ and the server runs 3.9.

Four tools, all limited to devotional data (services/devotion.py):
save_prayer, save_devotion, get_day, get_bible_progress. None of them can
delete anything or reach Medicine, Body, Food, Learnings or Emotions.
"""
import json
from datetime import date

from services import devotion

SERVER_NAME = "glad-codes-devotions"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")

INSTRUCTIONS = (
    "Saves Glad's prayers and morning devotions into her private glad.codes check-in, "
    "and reads them back. Save prayers exactly as spoken, word for word (keep filler "
    "words, repeated words and Tagalog; never clean up or translate). If a save returns "
    "needs_choice, ask Glad whether to replace what is there or add below it, then call "
    "the same tool again with if_exists set to her answer."
)

_DATE = {"type": "string", "format": "date",
         "description": "The day, YYYY-MM-DD, in Glad's timezone. Defaults to today. No future dates."}
_IF_EXISTS = {
    "type": "string", "enum": list(devotion.IF_EXISTS), "default": "ask",
    "description": "What to do if that box already has text. 'ask' (default) saves nothing and "
                   "returns needs_choice so you can ask Glad; then call again with 'replace' or 'add'.",
}
_VERSE = {"type": "object", "properties": {"text": {"type": "string"}, "ref": {"type": "string"}}}

TOOLS = [
    {
        "name": "save_prayer",
        "title": "Save prayer",
        "description": (
            "Save Glad's spoken prayer into Morning → My prayer or Evening → My prayer for a day. "
            "Send the prayer EXACTLY as she said it, word for word: keep filler words (um), "
            "repeated words and Tagalog. Do not clean up, summarize or translate. Also counts "
            "toward her prayer streak."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": _DATE,
                "part": {"type": "string", "enum": ["morning", "evening"],
                         "description": "Which prayer: the morning one or the evening one."},
                "prayer_text": {"type": "string", "description": "The prayer, word for word."},
                "if_exists": _IF_EXISTS,
            },
            "required": ["part", "prayer_text"],
            "additionalProperties": False,
        },
        "annotations": {"title": "Save prayer", "readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "save_devotion",
        "title": "Save morning devotion",
        "description": (
            "Save the morning devotion into the Devotion section of a day: the chapters read "
            "(fills Bible passage and counts toward Bible progress), the FULL written devotion "
            "as Markdown (the whole thing, not a summary) and its infographic as structured data. "
            "Only for the morning devotion's chapters, not the short night verses. Never changes "
            "Glad's own 'Thoughts on the devotion'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": _DATE,
                "chapters": {"type": "string",
                             "description": "Chapters read, e.g. \"Jeremiah 29, Psalm 37, Matthew 6-7\". "
                                            "Whole chapters; verse references count as their chapter."},
                "written_devotion": {"type": "string", "description": "The complete written devotion in Markdown."},
                "infographic": {
                    "type": "object",
                    "description": "The devotion's infographic as data; glad.codes draws it in its own style.",
                    "properties": {
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "key_verse": _VERSE,
                        "cards": {
                            "type": "array", "maxItems": 12,
                            "description": "One card per passage or idea.",
                            "items": {"type": "object", "properties": {
                                "label": {"type": "string", "description": "Short theme line, e.g. 'Seek him first'."},
                                "title": {"type": "string"},
                                "passage": {"type": "string", "description": "e.g. 'Matthew 6 & 7'."},
                                "summary": {"type": "string"},
                                "quote": {"type": "string"},
                                "quote_ref": {"type": "string"},
                            }},
                        },
                        "tiles_heading": {"type": "string", "description": "e.g. 'How to wait today'."},
                        "tiles": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
                            "title": {"type": "string"}, "text": {"type": "string"}, "ref": {"type": "string"}}}},
                        "closing_verse": _VERSE,
                        "translation": {"type": "string", "description": "e.g. 'KJV'."},
                    },
                    "required": ["title"],
                },
                "if_exists": _IF_EXISTS,
            },
            "required": ["chapters", "written_devotion"],
            "additionalProperties": False,
        },
        "annotations": {"title": "Save morning devotion", "readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "get_day",
        "title": "Get a day's prayers and devotion",
        "description": "Read one day's morning prayer, evening prayer and Devotion section (Bible passage, "
                       "written devotion, infographic, and Glad's own thoughts). Nothing else from that day.",
        "inputSchema": {"type": "object", "properties": {"date": _DATE}, "additionalProperties": False},
        "annotations": {"title": "Get a day", "readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "get_bible_progress",
        "title": "Get Bible progress",
        "description": "How many of the Bible's 1,189 chapters Glad's saved morning devotions have covered, "
                       "and which chapters by book.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"title": "Get Bible progress", "readOnlyHint": True, "openWorldHint": False},
    },
]


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _day(args, today: date) -> date:
    value = args.get("date")
    if value in (None, ""):
        return today
    try:
        day = date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        day = None
    if day is None:
        raise devotion.DevotionError("date must be YYYY-MM-DD")
    if day > today:
        raise devotion.DevotionError(f"date can't be in the future (today is {today.isoformat()})")
    return day


def _needs_choice_message(what):
    return (f"This day already has {what}. Nothing was changed. Ask Glad: replace it, or add the new one "
            f"below it? Then call again with if_exists set to \"replace\" or \"add\".")


def call_tool(name, args, today: date) -> dict:
    """Run a tool; returns its structured result. DevotionError = bad input."""
    if not isinstance(args, dict):
        raise devotion.DevotionError("arguments must be an object")
    if name == "save_prayer":
        day = _day(args, today)
        part = args.get("part")
        result = devotion.save_prayer(day, part, args.get("prayer_text"), args.get("if_exists") or "ask")
        if result.get("needs_choice"):
            return {"saved": False, "needs_choice": True, "date": day.isoformat(),
                    "existing_prayer": result["existing"],
                    "message": _needs_choice_message(f"{'a morning' if part == 'morning' else 'an evening'} prayer")}
        return {"saved": True, "date": day.isoformat(), "part": part, "added_below_existing": result["added"]}
    if name == "save_devotion":
        day = _day(args, today)
        result = devotion.save_devotion(day, args.get("chapters"), args.get("written_devotion"),
                                        args.get("infographic"), args.get("if_exists") or "ask")
        if result.get("needs_choice"):
            return {"saved": False, "needs_choice": True, "date": day.isoformat(),
                    "existing_bible_passage": result["existing_passage"],
                    "existing_devotion_title": result["existing_title"],
                    "message": _needs_choice_message("a devotion")}
        return {"saved": True, "date": day.isoformat(), "bible_passage": result["bible_passage"],
                "chapters_recorded": result["chapters"], "added_below_existing": result["added"]}
    if name == "get_day":
        return devotion.get_day(_day(args, today))
    if name == "get_bible_progress":
        progress = devotion.bible_progress()
        return {"chapters_covered": progress["covered"], "total_chapters": progress["total"],
                "percent": progress["percent"], "books_started": progress["books_started"],
                "books_finished": progress["books_finished"], "chapters_by_book": progress["by_book"]}
    raise RpcError(-32602, f"Unknown tool: {name}")


def _tool_result(data, is_error=False):
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if isinstance(data, dict):
        result["structuredContent"] = data
    return result


def _dispatch(method, params, today_fn):
    if method == "initialize":
        asked = params.get("protocolVersion")
        return {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "glad.codes devotions", "version": SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        try:
            return _tool_result(call_tool(name, params.get("arguments") or {}, today_fn()))
        except devotion.DevotionError as err:
            return _tool_result(str(err), is_error=True)
    raise RpcError(-32601, f"Method not found: {method}")


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle_one(message, today_fn):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        if isinstance(message, dict) and "method" not in message and ("result" in message or "error" in message):
            return None  # a response to us; we never send requests, so ignore
        return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
    if "id" not in message:
        return None  # notification (e.g. notifications/initialized): no reply
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _error(message["id"], -32602, "params must be an object")
    try:
        return {"jsonrpc": "2.0", "id": message["id"], "result": _dispatch(message["method"], params, today_fn)}
    except RpcError as err:
        return _error(message["id"], err.code, err.message)


def handle(body, today_fn):
    """A JSON-RPC message or batch → the reply (None when nothing to send)."""
    if isinstance(body, list):
        replies = [r for r in (handle_one(m, today_fn) for m in body) if r is not None]
        return replies or None
    return handle_one(body, today_fn)

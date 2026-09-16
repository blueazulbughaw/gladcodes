"""Generic CRUD engine for flat, sort_order-based admin tables: timeline
milestones, projects, learning progress, toolbox, community links, page
links, speaking events, events attending, and stat counters.

`resource` (the URL segment) is only ever used as a lookup key into the
RESOURCES dict below — it is never concatenated into SQL directly. The
table/column identifiers that DO get interpolated into SQL always come
from RESOURCES, a fixed dict defined in this file, never from user input.
"""
from datetime import date, datetime, time

from flask import abort, redirect, render_template, request, url_for

from database.db import execute, query, query_one, utc_now

from . import admin_bp

ICON_CHOICES = [
    "rocket", "activity", "heart-handshake", "code-2", "flask-conical",
    "bar-chart-3", "pen-tool", "github", "linkedin", "instagram", "star",
    "book-open", "terminal", "database", "cloud", "zap", "target", "compass",
    "lightbulb", "wrench", "users", "globe", "coffee", "camera", "mic",
    "graduation-cap", "circle",
]
# "github"/"linkedin"/"instagram" are hand-embedded SVGs (see
# templates/public/_macros.html::dynamic_icon), not real Lucide icon names —
# Lucide dropped brand logos entirely. Every renderer of a user-picked icon
# (projects, toolbox, community) must go through dynamic_icon(), never a
# bare <i data-lucide="...">, or these three will silently render nothing.

RESOURCES = {
    "timeline": {
        "table": "timeline_milestones",
        "title": "Timeline",
        "order_by": "sort_order",
        "fields": [
            ("month_label", "text", "Month label"),
            ("title", "text", "Title"),
            ("description", "textarea", "Description"),
            ("is_done", "checkbox", "Done"),
            ("sort_order", "int", "Sort order"),
        ],
    },
    "projects": {
        "table": "projects",
        "title": "Projects",
        "order_by": "sort_order",
        "fields": [
            ("title", "text", "Title"),
            ("description", "textarea", "Description"),
            ("icon", "icon", "Icon"),
            ("status", "select", "Status"),
            ("progress_pct", "int", "Progress %"),
            ("url", "url", "Link"),
            ("sort_order", "int", "Sort order"),
        ],
        "select_options": {"status": ["in_progress", "experimental", "launched"]},
    },
    "learning": {
        "table": "learning_progress",
        "title": "Currently Learning",
        "order_by": "sort_order",
        "fields": [
            ("skill", "text", "Skill"),
            ("progress_pct", "int", "Progress %"),
            ("sort_order", "int", "Sort order"),
        ],
    },
    "toolbox": {
        "table": "toolbox_items",
        "title": "Toolbox",
        "order_by": "sort_order",
        "fields": [
            ("name", "text", "Name"),
            ("icon", "icon", "Icon"),
            ("url", "url", "URL"),
            ("sort_order", "int", "Sort order"),
        ],
    },
    "community": {
        "table": "community_links",
        "title": "Community",
        "order_by": "sort_order",
        "fields": [
            ("org_name", "text", "Organization"),
            ("url", "url", "URL"),
            ("icon", "icon", "Icon"),
            ("sort_order", "int", "Sort order"),
        ],
    },
    "links": {
        "table": "page_links",
        "title": "Links",
        "order_by": "sort_order",
        "fields": [
            ("label", "text", "Label"),
            ("url", "url", "URL"),
            ("sort_order", "int", "Sort order"),
            ("is_visible", "checkbox", "Visible"),
        ],
    },
    "speaking": {
        "table": "speaking_events",
        "title": "Speaking",
        "order_by": "event_date DESC",
        "fields": [
            ("title", "text", "Title"),
            ("event_name", "text", "Event"),
            ("event_date", "date", "Date"),
            ("link", "url", "Link"),
            ("description", "textarea", "Description"),
            ("sort_order", "int", "Sort order"),
        ],
    },
    "events": {
        "table": "attending_events",
        "title": "Events",
        # Nearest date first; rows with no datetime_from sort after every
        # dated row instead of floating to the top as MySQL's NULL-first
        # default.
        "order_by": "datetime_from IS NULL, datetime_from ASC",
        # Events has too many columns for a readable table — render the list
        # as cards instead. simple_list.html's card branch is written
        # against this resource's specific field names, not generic like the
        # table branch, so this flag only makes sense for a resource shaped
        # like this one.
        "list_view": "cards",
        # sort_order isn't in this list on purpose — events are ordered by
        # datetime_from (see order_by above), never manually reordered, so
        # exposing the column would just be a confusing no-op field. The
        # underlying attending_events.sort_order column stays (defaults to
        # 0 on every insert here) rather than being dropped.
        "fields": [
            ("event_name", "text", "Event"),
            ("attending_as", "text", "Attending As"),
            ("datetime_from", "datetime", "Start"),
            ("datetime_to", "datetime", "End"),
            ("status", "select", "Status"),
            ("location", "text", "Location"),
            ("link", "url", "Link"),
            ("description", "textarea", "Description"),
        ],
        "select_options": {"status": ["tentative", "confirmed"]},
    },
    "stats": {
        "table": "stat_counters",
        "title": "Stat Counters",
        "order_by": "sort_order",
        "fields": [
            ("label", "text", "Label"),
            ("value", "int", "Value"),
            ("suffix", "text", "Suffix"),
            ("sort_order", "int", "Sort order"),
        ],
    },
    "skills": {
        "table": "skills",
        "title": "Skills",
        "order_by": "sort_order",
        "fields": [
            ("category", "text", "Category (e.g. Engineering)"),
            ("skill_name", "text", "Skill"),
            ("sort_order", "int", "Sort order"),
        ],
    },
    "videos": {
        "table": "videos",
        "title": "Videos",
        "order_by": "sort_order",
        "fields": [
            ("title", "text", "Title"),
            ("youtube_url", "url", "YouTube URL"),
            ("description", "textarea", "Description"),
            ("published_at", "date", "Published date"),
            ("sort_order", "int", "Sort order"),
        ],
    },
    "instagram": {
        "table": "instagram_posts",
        "title": "Instagram / Reels",
        "order_by": "sort_order",
        "fields": [
            ("caption", "text", "Caption"),
            # Instagram's own embed snippet (blockquote + script tag) — kept
            # as trusted raw HTML, never bleach-sanitized, since sanitizing
            # would strip the script tag the embed needs to actually render.
            # Safe because only the authenticated admin can write this field.
            ("embed_code", "textarea", "Embed code (paste from Instagram's Embed button)"),
            ("posted_at", "date", "Posted date"),
            ("sort_order", "int", "Sort order"),
        ],
    },
}


def _get_resource(resource):
    config = RESOURCES.get(resource)
    if not config:
        abort(404)
    return config


def _parse_field(config, field_name, field_type):
    raw = request.form.get(field_name, "")
    if field_type == "checkbox":
        return 1 if raw == "on" else 0
    if field_type == "int":
        try:
            return int(raw)
        except ValueError:
            return 0
    if field_type == "date":
        try:
            return date.fromisoformat(raw) if raw else None
        except ValueError:
            return None
    if field_type == "time":
        try:
            return time.fromisoformat(raw) if raw else None
        except ValueError:
            return None
    if field_type == "datetime":
        # <input type="datetime-local"> posts "YYYY-MM-DDTHH:MM" (no
        # seconds) — fromisoformat accepts that directly.
        try:
            return datetime.fromisoformat(raw) if raw else None
        except ValueError:
            return None
    if field_type == "select":
        options = config.get("select_options", {}).get(field_name, [])
        return raw if raw in options else (options[0] if options else raw)
    if field_type == "url":
        return raw.strip() or None
    if field_type == "icon":
        cleaned = "".join(c for c in raw.strip().lower() if c.isalnum() or c == "-")
        return cleaned or "circle"
    return raw.strip()


def _split_upcoming_past(rows):
    """Split date-ordered rows into upcoming (including undated/TBA) and
    past, nearest-first in both directions — events-only (list_view: cards),
    same as the card template's field names."""
    now = utc_now()
    upcoming, past = [], []
    for row in rows:
        end = row["datetime_to"] or row["datetime_from"]
        (upcoming if end is None or end >= now else past).append(row)
    past.reverse()
    return upcoming, past


@admin_bp.route("/<resource>")
def simple_list(resource):
    config = _get_resource(resource)
    rows = query(f"SELECT * FROM {config['table']} ORDER BY {config['order_by']}")
    context = {"resource": resource, "config": config, "rows": rows, "icon_choices": ICON_CHOICES}
    if config.get("list_view") == "cards":
        context["upcoming_rows"], context["past_rows"] = _split_upcoming_past(rows)
    return render_template("simple_list.html", **context)


@admin_bp.route("/<resource>/create", methods=["POST"])
def simple_create(resource):
    config = _get_resource(resource)
    columns = [name for name, _, _ in config["fields"]]
    values = [_parse_field(config, name, ftype) for name, ftype, _ in config["fields"]]
    placeholders = ", ".join(["%s"] * len(columns))
    execute(
        f"INSERT INTO {config['table']} ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(values),
    )
    return redirect(url_for("admin.simple_list", resource=resource))


@admin_bp.route("/<resource>/<int:row_id>/edit", methods=["GET", "POST"])
def simple_edit(resource, row_id):
    config = _get_resource(resource)
    if request.method == "POST":
        assignments = ", ".join(f"{name} = %s" for name, _, _ in config["fields"])
        values = [_parse_field(config, name, ftype) for name, ftype, _ in config["fields"]]
        execute(
            f"UPDATE {config['table']} SET {assignments} WHERE id = %s",
            tuple(values) + (row_id,),
        )
        return redirect(url_for("admin.simple_list", resource=resource))

    row = query_one(f"SELECT * FROM {config['table']} WHERE id = %s", (row_id,))
    if not row:
        abort(404)
    return render_template(
        "simple_edit.html", resource=resource, config=config, row=row, icon_choices=ICON_CHOICES
    )


@admin_bp.route("/<resource>/<int:row_id>/delete", methods=["POST"])
def simple_delete(resource, row_id):
    config = _get_resource(resource)
    execute(f"DELETE FROM {config['table']} WHERE id = %s", (row_id,))
    return redirect(url_for("admin.simple_list", resource=resource))

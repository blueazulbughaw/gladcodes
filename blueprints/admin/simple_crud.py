"""Generic CRUD engine for flat, sort_order-based admin tables: timeline
milestones, projects, learning progress, toolbox, community links, page
links, events attending, and stat counters.

`resource` (the URL segment) is only ever used as a lookup key into the
RESOURCES dict below — it is never concatenated into SQL directly. The
table/column identifiers that DO get interpolated into SQL always come
from RESOURCES, a fixed dict defined in this file, never from user input.
"""
from datetime import date, datetime, time

from flask import abort, redirect, render_template, request, url_for

from database.db import execute, query, query_one, transaction, utc_now

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
        "list_view": "cards",
        "add_via_page": True,
        "card_title_field": "title",
        # Drag cards to reorder instead of typing a sort_order number — see
        # simple_reorder() below. The column itself stays (schema.sql never
        # drops columns); it's just no longer a form field.
        "reorderable": True,
        "fields": [
            ("month_label", "text", "Month label"),
            ("title", "text", "Title"),
            ("description", "textarea", "Description"),
            ("is_done", "checkbox", "Done"),
        ],
    },
    "projects": {
        "table": "projects",
        "title": "Projects",
        "order_by": "sort_order",
        "list_view": "cards",
        "add_via_page": True,
        "card_title_field": "title",
        "reorderable": True,
        "fields": [
            ("title", "text", "Title"),
            ("description", "textarea", "Description"),
            ("icon", "icon", "Icon"),
            ("status", "select", "Status"),
            ("progress_pct", "int", "Progress %"),
            ("url", "url", "Link"),
        ],
        "select_options": {"status": ["in_progress", "experimental", "launched"]},
    },
    "learning": {
        "table": "learning_progress",
        "title": "Currently Learning",
        "order_by": "sort_order",
        "list_view": "cards",
        "add_via_page": True,
        "card_title_field": "skill",
        "reorderable": True,
        "fields": [
            ("skill", "text", "Skill"),
            ("progress_pct", "int", "Progress %"),
        ],
    },
    "toolbox": {
        "table": "toolbox_items",
        "title": "Toolbox",
        "order_by": "sort_order",
        "list_view": "cards",
        "add_via_page": True,
        "card_title_field": "name",
        "reorderable": True,
        "fields": [
            ("name", "text", "Name"),
            ("icon", "icon", "Icon"),
            ("url", "url", "URL"),
        ],
    },
    "community": {
        "table": "community_links",
        "title": "Community",
        "order_by": "sort_order",
        "list_view": "cards",
        "add_via_page": True,
        "card_title_field": "org_name",
        "reorderable": True,
        "fields": [
            ("org_name", "text", "Organization"),
            ("url", "url", "URL"),
            ("icon", "icon", "Icon"),
        ],
    },
    "links": {
        "table": "page_links",
        "title": "Links",
        "order_by": "sort_order",
        "list_view": "cards",
        "add_via_page": True,
        "card_title_field": "label",
        "reorderable": True,
        "fields": [
            ("label", "text", "Label"),
            ("url", "url", "URL"),
            ("is_visible", "checkbox", "Visible"),
        ],
    },
    "events": {
        "table": "attending_events",
        "title": "Events",
        # Nearest date first; rows with no datetime_from sort after every
        # dated row instead of floating to the top as MySQL's NULL-first
        # default.
        "order_by": "datetime_from IS NULL, datetime_from ASC",
        # Events has its own upcoming/past split and TBA-date handling that
        # the generic "cards" card (used by Timeline, Projects, etc.) can't
        # express, so it gets a distinct list_view with hand-written markup
        # in simple_list.html rather than the generic card macro.
        "list_view": "event_cards",
        # Adding an event opens its own page (like the bespoke Journal/
        # Tutorials editors) instead of an inline form at the bottom of the
        # list — the list is a wall of cards, not a short table, so an
        # inline form there is easy to miss and awkward to scroll to.
        "add_via_page": True,
        "add_button_label": "Add an Event",
        # sort_order isn't in this list on purpose — events are ordered by
        # datetime_from (see order_by above), never manually reordered, so
        # exposing the column would just be a confusing no-op field. The
        # underlying attending_events.sort_order column stays (defaults to
        # 0 on every insert here) rather than being dropped.
        "fields": [
            ("event_name", "text", "Event"),
            ("attending_as", "select", "Attending As"),
            ("datetime_from", "datetime", "Start"),
            ("datetime_to", "datetime", "End"),
            ("status", "select", "Status"),
            ("location", "text", "Location"),
            ("link", "url", "Link"),
            ("description", "textarea", "Description"),
        ],
        "select_options": {
            "attending_as": ["Volunteer", "Speaker", "Attendee", "Organizer"],
            "status": ["tentative", "confirmed"],
        },
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
        "list_view": "cards",
        "add_via_page": True,
        "card_title_field": "skill_name",
        "reorderable": True,
        "fields": [
            ("category", "text", "Category (e.g. Engineering)"),
            ("skill_name", "text", "Skill"),
        ],
    },
    "videos": {
        "table": "videos",
        "title": "Videos",
        "order_by": "sort_order",
        "list_view": "cards",
        "add_via_page": True,
        "card_title_field": "title",
        "reorderable": True,
        "fields": [
            ("title", "text", "Title"),
            ("youtube_url", "url", "YouTube URL"),
            ("description", "textarea", "Description"),
            ("published_at", "date", "Published date"),
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
    past, nearest-first in both directions — events-only
    (list_view: event_cards), same as the card template's field names."""
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
    if config.get("list_view") == "event_cards":
        context["upcoming_rows"], context["past_rows"] = _split_upcoming_past(rows)
    return render_template("simple_list.html", **context)


@admin_bp.route("/<resource>/create", methods=["GET", "POST"])
def simple_create(resource):
    config = _get_resource(resource)
    if request.method == "GET":
        # Only resources with add_via_page (currently just Events) link here
        # for GET — others still use the inline form on simple_list.html —
        # but the route itself works generically for any resource.
        return render_template(
            "simple_new.html", resource=resource, config=config, icon_choices=ICON_CHOICES
        )
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


@admin_bp.route("/<resource>/reorder", methods=["POST"])
def simple_reorder(resource):
    """Persists a drag-and-drop card reorder as new sort_order values —
    the dragged-to DOM order, sent as repeated `id` fields, becomes each
    row's new sort_order (0-indexed)."""
    config = _get_resource(resource)
    if not config.get("reorderable"):
        abort(404)
    ids = request.form.getlist("id")
    with transaction() as cursor:
        for index, row_id in enumerate(ids):
            cursor.execute(
                f"UPDATE {config['table']} SET sort_order = %s WHERE id = %s", (index, row_id)
            )
    return ("", 204)

from collections import OrderedDict
from datetime import datetime, timezone

from flask import render_template

from database.db import query, query_one

from . import public_bp

# Full pages (journal, projects, dashboard, resume, speaking, links,
# resources, contact, about) are built in later steps.


@public_bp.app_context_processor
def inject_globals():
    return {"current_year": datetime.now(timezone.utc).year}


@public_bp.context_processor
def inject_site_settings():
    rows = query("SELECT setting_key, setting_value FROM site_settings")
    return {"settings": {row["setting_key"]: row["setting_value"] for row in rows}}


@public_bp.route("/")
def home():
    now = query_one("SELECT * FROM now_card WHERE id = 1")
    stats = query("SELECT * FROM stat_counters ORDER BY sort_order")
    projects = query("SELECT * FROM projects ORDER BY sort_order")
    journal_posts = query(
        """
        SELECT * FROM journal_posts
        WHERE status = 'published'
        ORDER BY published_at DESC
        LIMIT 4
        """
    )
    milestones = query("SELECT * FROM timeline_milestones ORDER BY sort_order")

    timeline_by_month = OrderedDict()
    for milestone in milestones:
        timeline_by_month.setdefault(milestone["month_label"], []).append(milestone)

    return render_template(
        "home.html",
        now=now,
        stats=stats,
        projects=projects,
        journal_posts=journal_posts,
        timeline_by_month=list(timeline_by_month.items()),
    )

import re
from collections import OrderedDict
from datetime import datetime, timezone

from flask import abort, flash, redirect, render_template, request, url_for

from database.db import execute, query, query_one
from services.content import render_markdown
from services.github import get_profile_summary
from services.metrics import get_chart_series

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

from . import public_bp

# /about and /resources are Phase 1 placeholder pages (Phase 2 content per
# spec). /contact has no dedicated page — "work with me" is a mailto link
# in the footer, wired via site_settings.contact_email.


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
    learning = query("SELECT * FROM learning_progress ORDER BY sort_order")
    toolbox = query("SELECT * FROM toolbox_items ORDER BY sort_order")
    community = query("SELECT * FROM community_links ORDER BY sort_order")
    coding_hours = get_chart_series("coding_hours_weekly")

    timeline_by_month = OrderedDict()
    for milestone in milestones:
        timeline_by_month.setdefault(milestone["month_label"], []).append(milestone)

    github_row = query_one("SELECT setting_value FROM site_settings WHERE setting_key = 'github_username'")
    github = get_profile_summary(github_row["setting_value"] if github_row else None)
    if github:
        for repo in github["repos"]:
            if repo.get("pushed_at"):
                repo["pushed_at_parsed"] = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))

    return render_template(
        "home.html",
        now=now,
        stats=stats,
        projects=projects,
        journal_posts=journal_posts,
        timeline_by_month=list(timeline_by_month.items()),
        learning=learning,
        toolbox=toolbox,
        community=community,
        coding_hours=coding_hours,
        github=github,
    )


@public_bp.route("/dashboard")
def dashboard():
    stats = query("SELECT * FROM stat_counters ORDER BY sort_order")
    coding_hours = get_chart_series("coding_hours_weekly")
    features_shipped = get_chart_series("features_shipped_monthly")
    learning_metrics = get_chart_series("learning_metrics")

    beta_rows = query("SELECT period_label, value FROM chart_metrics WHERE metric_key = 'beta_users'")
    beta = {row["period_label"]: float(row["value"]) for row in beta_rows}
    beta_current = beta.get("current", 0)
    beta_target = beta.get("target", 0)
    beta_pct = round(beta_current / beta_target * 100) if beta_target else 0

    return render_template(
        "dashboard.html",
        stats=stats,
        coding_hours=coding_hours,
        features_shipped=features_shipped,
        learning_metrics=learning_metrics,
        beta_current=beta_current,
        beta_target=beta_target,
        beta_pct=beta_pct,
    )


@public_bp.route("/journal")
def journal_index():
    q = request.args.get("q", "").strip()
    tag = request.args.get("tag", "").strip()

    sql = "SELECT * FROM journal_posts WHERE status = 'published'"
    params = []
    if q:
        sql += " AND title LIKE %s"
        params.append(f"%{q}%")
    if tag:
        sql += " AND FIND_IN_SET(%s, tags)"
        params.append(tag)
    sql += " ORDER BY published_at DESC"
    posts = query(sql, tuple(params))

    tag_rows = query(
        "SELECT tags FROM journal_posts WHERE status = 'published' AND tags IS NOT NULL AND tags != ''"
    )
    all_tags = sorted({t.strip() for row in tag_rows for t in row["tags"].split(",") if t.strip()})

    return render_template("journal_index.html", posts=posts, all_tags=all_tags, q=q, active_tag=tag)


@public_bp.route("/journal/<slug>")
def journal_post(slug):
    post = query_one(
        "SELECT * FROM journal_posts WHERE slug = %s AND status = 'published'",
        (slug,),
    )
    if not post:
        abort(404)
    content_html = render_markdown(post["content_markdown"])
    return render_template("journal_post.html", post=post, content_html=content_html)


@public_bp.route("/projects")
def projects_index():
    projects = query("SELECT * FROM projects ORDER BY sort_order")
    return render_template("projects.html", projects=projects)


@public_bp.route("/speaking")
def speaking():
    events = query("SELECT * FROM speaking_events ORDER BY event_date DESC")
    return render_template("speaking.html", events=events)


@public_bp.route("/links")
def links_page():
    links = query("SELECT * FROM page_links WHERE is_visible = 1 ORDER BY sort_order")
    return render_template("links.html", links=links)


@public_bp.route("/resume")
def resume():
    meta = query_one("SELECT * FROM resume_meta WHERE id = 1")
    return render_template("resume.html", meta=meta)


@public_bp.route("/about")
def about():
    return render_template("about.html")


@public_bp.route("/resources")
def resources():
    return render_template("resources.html")


@public_bp.route("/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    email = request.form.get("email", "").strip().lower()
    if not EMAIL_RE.match(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("public.home") + "#newsletter")

    # Dedupe via ON DUPLICATE KEY UPDATE against the unique email column —
    # re-subscribing just reactivates instead of erroring or double-inserting.
    execute(
        """
        INSERT INTO subscribers (email, is_active) VALUES (%s, 1)
        ON DUPLICATE KEY UPDATE is_active = 1
        """,
        (email,),
    )
    flash("Thanks for subscribing — you're on the list.", "success")
    return redirect(url_for("public.home") + "#newsletter")

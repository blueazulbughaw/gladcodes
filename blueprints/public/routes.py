import re
from collections import OrderedDict
from datetime import datetime, timezone

from flask import Response, abort, current_app, flash, redirect, render_template, request, url_for

from database.db import execute, query, query_one, utc_now
from services.content import render_markdown
from services.github import get_profile_summary
from services.mail import send_contact_email
from services.metrics import get_chart_series

from . import public_bp

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CONTACT_SUBJECTS = [
    "I Have a Job for You",
    "I Want to Fund Your Idea",
    "Let's Create Something Awesome",
    "Can I Buy You a Drink?",
    "I Need Your Expertise",
    "Promote My Product",
    "Just want to say Hi!",
    "Surprise Me",
]

# /about and /resources are Phase 1 placeholder pages (Phase 2 content per
# spec).


@public_bp.app_context_processor
def inject_globals():
    return {"current_year": datetime.now(timezone.utc).year}


def _normalize_github_username(value):
    """github_username is meant to be a bare username, but admins sometimes
    paste the full profile URL instead — accept both so a data-entry slip
    doesn't break the profile link or the GitHub API call."""
    if not value:
        return None
    value = value.strip().rstrip("/")
    if value.startswith("http://") or value.startswith("https://"):
        value = value.rsplit("/", 1)[-1]
    return value or None


@public_bp.context_processor
def inject_site_globals():
    rows = query("SELECT setting_key, setting_value FROM site_settings")
    settings_map = {row["setting_key"]: row["setting_value"] for row in rows}
    base_url = current_app.config["PUBLIC_SITE_URL"].rstrip("/")
    github_username = _normalize_github_username(settings_map.get("github_username"))
    github_url = f"https://github.com/{github_username}" if github_username else None

    same_as = [settings_map[k] for k in ("linkedin_url", "instagram_url") if settings_map.get(k)]
    if github_url:
        same_as.append(github_url)

    person_ld = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": "Glad",
        "url": base_url,
        "jobTitle": "Software Engineer, Technical Program Manager, Founder",
        "sameAs": same_as,
    }
    website_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": settings_map.get("site_title", "GladCodes"),
        "url": base_url,
        "description": settings_map.get("site_description", ""),
    }
    return {
        "settings": settings_map,
        "site_url": base_url,
        "github_url": github_url,
        "person_ld": person_ld,
        "website_ld": website_ld,
    }


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
    github_username = _normalize_github_username(github_row["setting_value"] if github_row else None)
    github = get_profile_summary(github_username)
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


@public_bp.route("/events")
def events_index():
    # Every event I'm involved in — attending, volunteering, organizing, or
    # speaking at (see attending_as) — now lives in one list; the separate
    # /speaking page was folded in here.
    # Nearest date first; undated rows sort to the bottom instead of the top
    # (MySQL's default for ORDER BY ... ASC on a nullable column).
    events = query("SELECT * FROM attending_events ORDER BY datetime_from IS NULL, datetime_from ASC")

    # Split into Upcoming (including undated/TBA rows — better to surface
    # them than bury them under events that already happened) and Past
    # (nearest-first, so reverse the ascending order above).
    now = utc_now()
    upcoming_events, past_events = [], []
    for event in events:
        end = event["datetime_to"] or event["datetime_from"]
        (upcoming_events if end is None or end >= now else past_events).append(event)
    past_events.reverse()

    return render_template("events.html", upcoming_events=upcoming_events, past_events=past_events)


@public_bp.route("/lets-connect")
def lets_connect():
    links = query("SELECT * FROM page_links WHERE is_visible = 1 ORDER BY sort_order")
    headshot_row = query_one("SELECT setting_value FROM site_settings WHERE setting_key = 'headshot_image'")
    headshot = headshot_row["setting_value"] if headshot_row else None
    return render_template("links.html", links=links, headshot=headshot)


@public_bp.route("/resume")
def resume():
    meta = query_one("SELECT * FROM resume_meta WHERE id = 1")

    skill_rows = query("SELECT * FROM skills ORDER BY sort_order")
    skills_by_category = OrderedDict()
    for row in skill_rows:
        skills_by_category.setdefault(row["category"], []).append(row["skill_name"])

    return render_template("resume.html", meta=meta, skills_by_category=skills_by_category)


@public_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        # Honeypot: a hidden field real visitors never fill in. A bot that
        # fills every field trips this — pretend success, send nothing.
        if request.form.get("company"):
            flash("Thanks — I'll get back to you soon.", "success")
            return redirect(url_for("public.contact"))

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject_choice = request.form.get("subject", "")
        message = request.form.get("message", "").strip()

        errors = []
        if not name:
            errors.append("Please enter your name.")
        if not EMAIL_RE.match(email):
            errors.append("Please enter a valid email address.")
        if subject_choice not in CONTACT_SUBJECTS:
            errors.append("Please choose a subject.")
        if not message:
            errors.append("Please enter a message.")
        elif len(message) > 5000:
            errors.append("Message is too long (max 5000 characters).")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("contact.html", subjects=CONTACT_SUBJECTS, form=request.form)

        if send_contact_email(name, email, subject_choice, message):
            flash("Thanks — I'll get back to you soon.", "success")
        else:
            flash("Something went wrong sending your message — please email me directly instead.", "error")
        return redirect(url_for("public.contact"))

    return render_template("contact.html", subjects=CONTACT_SUBJECTS, form={})


@public_bp.route("/tutorials")
def tutorials_index():
    series = request.args.get("series", "").strip()

    sql = "SELECT * FROM tutorials WHERE status = 'published'"
    params = []
    if series:
        sql += " AND series_name = %s"
        params.append(series)
    sql += " ORDER BY published_at DESC"
    tutorials = query(sql, tuple(params))

    series_rows = query(
        "SELECT DISTINCT series_name FROM tutorials WHERE status = 'published' AND series_name IS NOT NULL AND series_name != ''"
    )
    all_series = sorted(row["series_name"] for row in series_rows)

    return render_template("tutorials_index.html", tutorials=tutorials, all_series=all_series, active_series=series)


@public_bp.route("/tutorials/<slug>")
def tutorial_detail(slug):
    tutorial = query_one(
        "SELECT * FROM tutorials WHERE slug = %s AND status = 'published'",
        (slug,),
    )
    if not tutorial:
        abort(404)
    content_html = render_markdown(tutorial["content_markdown"])

    series_tutorials = []
    if tutorial["series_name"]:
        series_tutorials = query(
            """
            SELECT title, slug FROM tutorials
            WHERE series_name = %s AND status = 'published'
            ORDER BY published_at ASC
            """,
            (tutorial["series_name"],),
        )

    return render_template(
        "tutorial_detail.html", tutorial=tutorial, content_html=content_html, series_tutorials=series_tutorials
    )


@public_bp.route("/videos")
def videos_index():
    videos = query("SELECT * FROM videos ORDER BY published_at DESC, sort_order")
    instagram_posts = query("SELECT * FROM instagram_posts ORDER BY posted_at DESC, sort_order")
    return render_template("videos.html", videos=videos, instagram_posts=instagram_posts)


@public_bp.route("/about")
def about():
    return render_template("about.html")


@public_bp.route("/resources")
def resources():
    pdf_assets = query("SELECT * FROM pdf_assets ORDER BY created_at DESC")
    latest_tutorials = query(
        "SELECT title, slug, excerpt FROM tutorials WHERE status = 'published' ORDER BY published_at DESC LIMIT 3"
    )
    latest_videos = query("SELECT title, youtube_url FROM videos ORDER BY published_at DESC, sort_order LIMIT 3")
    return render_template(
        "resources.html", pdf_assets=pdf_assets, latest_tutorials=latest_tutorials, latest_videos=latest_videos
    )


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


@public_bp.route("/sitemap.xml")
def sitemap():
    base_url = current_app.config["PUBLIC_SITE_URL"].rstrip("/")
    static_endpoints = [
        "public.home", "public.journal_index", "public.projects_index",
        "public.dashboard", "public.resume", "public.events_index",
        "public.lets_connect", "public.contact", "public.about", "public.resources",
        "public.tutorials_index", "public.videos_index",
    ]
    urls = [{"loc": base_url + url_for(endpoint), "lastmod": None} for endpoint in static_endpoints]

    posts = query("SELECT slug, updated_at FROM journal_posts WHERE status = 'published'")
    urls += [
        {"loc": f"{base_url}{url_for('public.journal_post', slug=post['slug'])}", "lastmod": post["updated_at"]}
        for post in posts
    ]

    tutorials = query("SELECT slug, updated_at FROM tutorials WHERE status = 'published'")
    urls += [
        {"loc": f"{base_url}{url_for('public.tutorial_detail', slug=tutorial['slug'])}", "lastmod": tutorial["updated_at"]}
        for tutorial in tutorials
    ]

    xml = render_template("sitemap.xml", urls=urls)
    return Response(xml, mimetype="application/xml")


@public_bp.route("/robots.txt")
def robots():
    base_url = current_app.config["PUBLIC_SITE_URL"].rstrip("/")
    body = (
        "User-agent: *\n"
        "Disallow: /gc-admin/\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain")

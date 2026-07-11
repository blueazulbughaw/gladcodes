from flask import abort, redirect, render_template, request, url_for

from database.db import execute, query, query_one, utc_now
from services.content import slugify

from . import admin_bp
from .uploads import save_image


def _valid_status(value):
    return value if value in ("draft", "published") else "draft"


@admin_bp.route("/tutorials")
def tutorials_index():
    tutorials = query("SELECT * FROM tutorials ORDER BY created_at DESC")
    return render_template("tutorials_list.html", tutorials=tutorials)


@admin_bp.route("/tutorials/new", methods=["GET", "POST"])
def tutorials_new():
    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = slugify(request.form.get("slug", "").strip() or title)
        series_name = request.form.get("series_name", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        content_markdown = request.form.get("content_markdown", "")
        status = _valid_status(request.form.get("status"))

        cover_filename = None
        file = request.files.get("cover_image")
        if file and file.filename:
            cover_filename, error = save_image(file)

        if not error:
            published_at = utc_now() if status == "published" else None
            execute(
                """
                INSERT INTO tutorials
                    (slug, title, series_name, excerpt, content_markdown, cover_image, status, published_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (slug, title, series_name, excerpt, content_markdown, cover_filename, status, published_at),
            )
            return redirect(url_for("admin.tutorials_index"))

    return render_template("tutorials_form.html", tutorial=None, error=error)


@admin_bp.route("/tutorials/<int:tutorial_id>/edit", methods=["GET", "POST"])
def tutorials_edit(tutorial_id):
    tutorial = query_one("SELECT * FROM tutorials WHERE id = %s", (tutorial_id,))
    if not tutorial:
        abort(404)

    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = slugify(request.form.get("slug", "").strip() or title)
        series_name = request.form.get("series_name", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        content_markdown = request.form.get("content_markdown", "")
        status = _valid_status(request.form.get("status"))

        cover_filename = tutorial["cover_image"]
        file = request.files.get("cover_image")
        if file and file.filename:
            saved_filename, error = save_image(file)
            if not error:
                cover_filename = saved_filename

        if not error:
            published_at = tutorial["published_at"]
            if status == "published" and published_at is None:
                published_at = utc_now()

            execute(
                """
                UPDATE tutorials
                SET slug = %s, title = %s, series_name = %s, excerpt = %s, content_markdown = %s,
                    cover_image = %s, status = %s, published_at = %s
                WHERE id = %s
                """,
                (slug, title, series_name, excerpt, content_markdown, cover_filename, status, published_at, tutorial_id),
            )
            return redirect(url_for("admin.tutorials_index"))
        tutorial = {**tutorial, "title": title, "slug": slug, "series_name": series_name,
                    "excerpt": excerpt, "content_markdown": content_markdown, "status": status}

    return render_template("tutorials_form.html", tutorial=tutorial, error=error)


@admin_bp.route("/tutorials/<int:tutorial_id>/delete", methods=["POST"])
def tutorials_delete(tutorial_id):
    execute("DELETE FROM tutorials WHERE id = %s", (tutorial_id,))
    return redirect(url_for("admin.tutorials_index"))

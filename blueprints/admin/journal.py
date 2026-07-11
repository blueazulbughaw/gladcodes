from flask import abort, redirect, render_template, request, url_for

from database.db import execute, query, query_one, utc_now
from services.content import render_markdown, slugify

from . import admin_bp
from .uploads import save_image


def _valid_status(value):
    return value if value in ("draft", "published") else "draft"


@admin_bp.route("/journal")
def journal_index():
    posts = query("SELECT * FROM journal_posts ORDER BY created_at DESC")
    return render_template("journal_list.html", posts=posts)


@admin_bp.route("/journal/new", methods=["GET", "POST"])
def journal_new():
    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = slugify(request.form.get("slug", "").strip() or title)
        excerpt = request.form.get("excerpt", "").strip()
        content_markdown = request.form.get("content_markdown", "")
        tags = request.form.get("tags", "").strip()
        status = _valid_status(request.form.get("status"))

        cover_filename = None
        file = request.files.get("cover_image")
        if file and file.filename:
            cover_filename, error = save_image(file)

        if not error:
            published_at = utc_now() if status == "published" else None
            execute(
                """
                INSERT INTO journal_posts
                    (slug, title, excerpt, content_markdown, cover_image, tags, status, published_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (slug, title, excerpt, content_markdown, cover_filename, tags, status, published_at),
            )
            return redirect(url_for("admin.journal_index"))

    return render_template("journal_form.html", post=None, error=error)


@admin_bp.route("/journal/<int:post_id>/edit", methods=["GET", "POST"])
def journal_edit(post_id):
    post = query_one("SELECT * FROM journal_posts WHERE id = %s", (post_id,))
    if not post:
        abort(404)

    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = slugify(request.form.get("slug", "").strip() or title)
        excerpt = request.form.get("excerpt", "").strip()
        content_markdown = request.form.get("content_markdown", "")
        tags = request.form.get("tags", "").strip()
        status = _valid_status(request.form.get("status"))

        cover_filename = post["cover_image"]
        file = request.files.get("cover_image")
        if file and file.filename:
            saved_filename, error = save_image(file)
            if not error:
                cover_filename = saved_filename

        if not error:
            published_at = post["published_at"]
            if status == "published" and published_at is None:
                published_at = utc_now()

            execute(
                """
                UPDATE journal_posts
                SET slug = %s, title = %s, excerpt = %s, content_markdown = %s,
                    cover_image = %s, tags = %s, status = %s, published_at = %s
                WHERE id = %s
                """,
                (slug, title, excerpt, content_markdown, cover_filename, tags, status, published_at, post_id),
            )
            return redirect(url_for("admin.journal_index"))
        # Re-render with the attempted (unsaved) values so the upload error
        # doesn't discard the rest of the edit.
        post = {**post, "title": title, "slug": slug, "excerpt": excerpt,
                "content_markdown": content_markdown, "tags": tags, "status": status}

    return render_template("journal_form.html", post=post, error=error)


@admin_bp.route("/journal/<int:post_id>/delete", methods=["POST"])
def journal_delete(post_id):
    execute("DELETE FROM journal_posts WHERE id = %s", (post_id,))
    return redirect(url_for("admin.journal_index"))


@admin_bp.route("/journal/preview", methods=["POST"])
def journal_preview():
    return render_markdown(request.form.get("markdown", ""))

from flask import abort, redirect, render_template, request, url_for

from database.db import execute, query, query_one

from . import admin_bp
from .uploads import save_resume_pdf


def _to_price(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


@admin_bp.route("/pdf-library")
def pdf_library_index():
    assets = query("SELECT * FROM pdf_assets ORDER BY created_at DESC")
    return render_template("pdf_library_list.html", assets=assets)


@admin_bp.route("/pdf-library/new", methods=["GET", "POST"])
def pdf_library_new():
    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        is_product = 1 if request.form.get("is_product") == "on" else 0
        price = _to_price(request.form.get("price"))

        file = request.files.get("pdf_file")
        filename, error = save_resume_pdf(file)

        if not error:
            execute(
                """
                INSERT INTO pdf_assets (title, file_path, is_product, price, description)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (title, filename, is_product, price, description),
            )
            return redirect(url_for("admin.pdf_library_index"))

    return render_template("pdf_library_form.html", asset=None, error=error)


@admin_bp.route("/pdf-library/<int:asset_id>/edit", methods=["GET", "POST"])
def pdf_library_edit(asset_id):
    asset = query_one("SELECT * FROM pdf_assets WHERE id = %s", (asset_id,))
    if not asset:
        abort(404)

    error = None
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        is_product = 1 if request.form.get("is_product") == "on" else 0
        price = _to_price(request.form.get("price"))

        file_path = asset["file_path"]
        file = request.files.get("pdf_file")
        if file and file.filename:
            filename, error = save_resume_pdf(file)
            if not error:
                file_path = filename

        if not error:
            execute(
                """
                UPDATE pdf_assets
                SET title = %s, file_path = %s, is_product = %s, price = %s, description = %s
                WHERE id = %s
                """,
                (title, file_path, is_product, price, description, asset_id),
            )
            return redirect(url_for("admin.pdf_library_index"))
        asset = {**asset, "title": title, "description": description, "is_product": is_product, "price": price}

    return render_template("pdf_library_form.html", asset=asset, error=error)


@admin_bp.route("/pdf-library/<int:asset_id>/delete", methods=["POST"])
def pdf_library_delete(asset_id):
    execute("DELETE FROM pdf_assets WHERE id = %s", (asset_id,))
    return redirect(url_for("admin.pdf_library_index"))

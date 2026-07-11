from datetime import date

from flask import redirect, render_template, request, url_for

from database.db import execute, query_one

from . import admin_bp
from .uploads import save_resume_pdf


@admin_bp.route("/resume", methods=["GET", "POST"])
def resume_editor():
    error = None
    if request.method == "POST":
        meta = query_one("SELECT * FROM resume_meta WHERE id = 1")
        file_path = meta["file_path"] if meta else None

        file = request.files.get("resume_pdf")
        if file and file.filename:
            saved_filename, error = save_resume_pdf(file)
            if not error:
                file_path = saved_filename

        if not error:
            execute(
                "UPDATE resume_meta SET file_path = %s, last_updated = %s WHERE id = 1",
                (file_path, date.today()),
            )
            return redirect(url_for("admin.resume_editor"))

    meta = query_one("SELECT * FROM resume_meta WHERE id = 1")
    return render_template("resume_editor.html", meta=meta, error=error)

from flask import redirect, render_template, request, url_for

from database.db import execute, query

from . import admin_bp
from .uploads import save_image

SETTINGS_FIELDS = [
    ("github_username", "GitHub username"),
    ("linkedin_url", "LinkedIn URL"),
    ("instagram_url", "Instagram URL"),
    ("site_title", "Site title"),
    ("site_description", "Site description"),
    ("contact_email", "Contact email"),
]


def _upsert_setting(key, value):
    execute(
        """
        INSERT INTO site_settings (setting_key, setting_value) VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
        """,
        (key, value),
    )


@admin_bp.route("/settings", methods=["GET", "POST"])
def settings_editor():
    error = None
    if request.method == "POST":
        for key, _ in SETTINGS_FIELDS:
            _upsert_setting(key, request.form.get(key, "").strip())

        file = request.files.get("headshot_image")
        if file and file.filename:
            filename, error = save_image(file)
            if not error:
                _upsert_setting("headshot_image", filename)

        if not error:
            return redirect(url_for("admin.settings_editor"))

    rows = query("SELECT setting_key, setting_value FROM site_settings")
    current = {row["setting_key"]: row["setting_value"] for row in rows}
    return render_template("settings.html", fields=SETTINGS_FIELDS, current=current, error=error)

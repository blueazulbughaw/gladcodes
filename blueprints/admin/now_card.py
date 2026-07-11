from flask import redirect, render_template, request, url_for

from database.db import execute, query_one, utc_now

from . import admin_bp


@admin_bp.route("/now-card", methods=["GET", "POST"])
def now_card_editor():
    if request.method == "POST":
        execute(
            """
            UPDATE now_card
            SET location = %s, building = %s, drinking = %s, reading = %s,
                goal_this_week = %s, updated_at = %s
            WHERE id = 1
            """,
            (
                request.form.get("location", "").strip(),
                request.form.get("building", "").strip(),
                request.form.get("drinking", "").strip(),
                request.form.get("reading", "").strip(),
                request.form.get("goal_this_week", "").strip(),
                utc_now(),
            ),
        )
        return redirect(url_for("admin.now_card_editor"))

    now = query_one("SELECT * FROM now_card WHERE id = 1")
    return render_template("now_card.html", now=now)

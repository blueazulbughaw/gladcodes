import csv
import io

from flask import Response, redirect, render_template, url_for

from database.db import execute, query

from . import admin_bp


@admin_bp.route("/subscribers")
def subscribers_index():
    subscribers = query("SELECT * FROM subscribers ORDER BY subscribed_at DESC")
    return render_template("subscribers.html", subscribers=subscribers)


@admin_bp.route("/subscribers/<int:sub_id>/delete", methods=["POST"])
def subscribers_delete(sub_id):
    execute("DELETE FROM subscribers WHERE id = %s", (sub_id,))
    return redirect(url_for("admin.subscribers_index"))


@admin_bp.route("/subscribers/export.csv")
def subscribers_export():
    subscribers = query("SELECT email, subscribed_at, is_active FROM subscribers ORDER BY subscribed_at DESC")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["email", "subscribed_at", "is_active"])
    for row in subscribers:
        writer.writerow([row["email"], row["subscribed_at"], row["is_active"]])
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=subscribers.csv"},
    )

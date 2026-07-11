from flask import abort, redirect, render_template, request, url_for

from database.db import execute, query, query_one

from . import admin_bp

CHART_GROUPS = [
    ("coding_hours_weekly", "Coding hours (weekly)"),
    ("features_shipped_monthly", "Features shipped (monthly)"),
    ("learning_metrics", "Learning metrics (hours by skill)"),
    ("beta_users", "Beta users (current / target)"),
]
VALID_METRIC_KEYS = {key for key, _ in CHART_GROUPS}


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@admin_bp.route("/metrics")
def metrics_index():
    groups = []
    for key, label in CHART_GROUPS:
        rows = query(
            "SELECT * FROM chart_metrics WHERE metric_key = %s ORDER BY sort_order",
            (key,),
        )
        groups.append({"key": key, "label": label, "rows": rows})
    return render_template("metrics.html", groups=groups)


@admin_bp.route("/metrics/<metric_key>/create", methods=["POST"])
def metrics_create(metric_key):
    if metric_key not in VALID_METRIC_KEYS:
        abort(404)
    period_label = request.form.get("period_label", "").strip()
    value = _to_float(request.form.get("value"))
    sort_order = _to_int(request.form.get("sort_order"))
    execute(
        "INSERT INTO chart_metrics (metric_key, period_label, value, sort_order) VALUES (%s, %s, %s, %s)",
        (metric_key, period_label, value, sort_order),
    )
    return redirect(url_for("admin.metrics_index"))


@admin_bp.route("/metrics/<int:row_id>/edit", methods=["GET", "POST"])
def metrics_edit(row_id):
    row = query_one("SELECT * FROM chart_metrics WHERE id = %s", (row_id,))
    if not row:
        abort(404)
    if request.method == "POST":
        period_label = request.form.get("period_label", "").strip()
        value = _to_float(request.form.get("value"))
        sort_order = _to_int(request.form.get("sort_order"))
        execute(
            "UPDATE chart_metrics SET period_label = %s, value = %s, sort_order = %s WHERE id = %s",
            (period_label, value, sort_order, row_id),
        )
        return redirect(url_for("admin.metrics_index"))
    return render_template("metrics_edit.html", row=row)


@admin_bp.route("/metrics/<int:row_id>/delete", methods=["POST"])
def metrics_delete(row_id):
    execute("DELETE FROM chart_metrics WHERE id = %s", (row_id,))
    return redirect(url_for("admin.metrics_index"))

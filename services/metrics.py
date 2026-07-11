"""Shared chart-series lookup used by both the public dashboard/home teaser
and the admin dashboard snapshot.
"""
from database.db import query


def get_chart_series(metric_key):
    """labels/data pair for one chart_metrics series, in sort_order.

    Key is "data", not "values" — dict has a builtin .values() method, and
    Jinja's attribute-access fallback (foo.values) would silently return
    that bound method instead of the dict item.
    """
    rows = query(
        "SELECT period_label, value FROM chart_metrics WHERE metric_key = %s ORDER BY sort_order",
        (metric_key,),
    )
    return {
        "labels": [row["period_label"] for row in rows],
        "data": [float(row["value"]) for row in rows],
    }

"""Single shared PyMySQL access point. Every query in the app goes through
get_db()/query()/execute() here so parameterization stays consistent — never
build SQL with string formatting outside this module.
"""
import os
from contextlib import contextmanager
from datetime import datetime, timezone

import pymysql
import pymysql.cursors
from flask import current_app, g


def utc_now():
    """Naive UTC datetime for writing to DATETIME columns from Python.

    Prefer this over MySQL's NOW() when the app (not the DB) decides the
    timestamp: NOW() returns the DB server's local time, which silently
    breaks any comparison against datetime.now(timezone.utc) unless the
    server is configured for UTC — this bit github_cache's TTL check once
    already (see services/github.py).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=current_app.config["DB_HOST"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            database=current_app.config["DB_NAME"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
    return g.db


def close_db(_exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def query(sql: str, params: tuple = ()):
    """SELECT helper. Returns a list of dict rows."""
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def query_one(sql: str, params: tuple = ()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    """INSERT/UPDATE/DELETE helper. Commits and returns lastrowid."""
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(sql, params)
    db.commit()
    return cursor.lastrowid


@contextmanager
def transaction():
    """Group several execute() calls into one commit/rollback unit.

    Usage:
        with transaction() as cursor:
            cursor.execute(...)
            cursor.execute(...)
    """
    db = get_db()
    cursor = db.cursor()
    try:
        yield cursor
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()


SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def schema_statements(sql_text: str):
    """Split schema.sql into statements. Full-line `--` comments are dropped
    first (some contain semicolons); the file never puts `;` inside string
    literals, which is what makes a plain split safe here."""
    lines = [line for line in sql_text.splitlines() if not line.lstrip().startswith("--")]
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


def apply_schema():
    """Run schema.sql (idempotent by design: CREATE TABLE IF NOT EXISTS,
    guarded seeds, ADD COLUMN IF NOT EXISTS). Called from passenger_wsgi.py
    on every app start, so a deploy never needs a manual phpMyAdmin import.
    Needs an app context."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        statements = schema_statements(f.read())
    with transaction() as cursor:
        for statement in statements:
            cursor.execute(statement)

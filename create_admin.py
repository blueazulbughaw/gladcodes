"""CLI to create or update the single gc-admin login.

Usage (server or local venv):
    python create_admin.py <username>

Prompts for a password with hidden input (getpass), enforces a 12-character
minimum, hashes it with bcrypt, and upserts it into admin_users.
"""
import getpass
import sys

import bcrypt
import pymysql

from config import Config

MIN_PASSWORD_LENGTH = 12


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python create_admin.py <username>")
        return 1

    username = sys.argv[1].strip()
    if not username:
        print("Username cannot be empty.")
        return 1

    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        return 1

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        return 1

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = pymysql.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO admin_users (username, password_hash)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash)
                """,
                (username, password_hash),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"Admin user '{username}' created/updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

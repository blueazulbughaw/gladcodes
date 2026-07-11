"""Shared upload validation/save for journal cover images and the resume
PDF. Files are validated by extension and size before touching disk, and
saved under a randomized filename (never the user-supplied name).
"""
import os
import secrets

from flask import current_app
from werkzeug.utils import secure_filename


def _validate_and_save(file_storage, allowed_extensions, max_bytes):
    """Returns (filename, error). Exactly one of the two is truthy."""
    if not file_storage or not file_storage.filename:
        return None, "No file selected."

    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_extensions:
        return None, f"File type .{ext or '?'} isn't allowed."

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > max_bytes:
        return None, f"File is too large (max {max_bytes // (1024 * 1024)} MB)."

    random_name = f"{secrets.token_hex(16)}.{ext}"
    dest = os.path.join(current_app.config["UPLOAD_FOLDER"], random_name)
    file_storage.save(dest)
    return random_name, None


def save_image(file_storage):
    return _validate_and_save(
        file_storage,
        current_app.config["ALLOWED_IMAGE_EXTENSIONS"],
        5 * 1024 * 1024,
    )


def save_resume_pdf(file_storage):
    return _validate_and_save(
        file_storage,
        current_app.config["ALLOWED_RESUME_EXTENSIONS"],
        10 * 1024 * 1024,
    )

from flask import Blueprint

# CRITICAL: this blueprint is never linked from any public template, is
# excluded from sitemap.xml, and every response must set
# X-Robots-Tag: noindex, nofollow (see app.py). See CLAUDE.md.
admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/gc-admin",
    template_folder="../../templates/admin",
)

from . import routes  # noqa: E402,F401

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
from . import simple_crud  # noqa: E402,F401
from . import now_card  # noqa: E402,F401
from . import journal  # noqa: E402,F401
from . import metrics  # noqa: E402,F401
from . import resume  # noqa: E402,F401
from . import settings  # noqa: E402,F401
from . import subscribers  # noqa: E402,F401

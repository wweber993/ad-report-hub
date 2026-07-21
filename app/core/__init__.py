from flask import Blueprint

core_bp = Blueprint("core", __name__)

from app.core import routes  # noqa: F401, E402

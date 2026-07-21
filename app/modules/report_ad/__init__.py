from flask import Blueprint

ad_bp = Blueprint("ad", __name__)

from app.modules.report_ad import routes  # noqa: F401, E402

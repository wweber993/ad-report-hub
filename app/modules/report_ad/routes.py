"""
AD Report Hub — Report AD Module Routes
"""

import logging
import os
from datetime import datetime

from flask import current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from app.utils import module_required
from app.modules.report_ad import ad_bp
from app.modules.report_ad.utils.data_manager import (
    calculate_iso_soc_compliance,
    calculate_stats,
    load_all_users,
    write_json,
)

logger = logging.getLogger(__name__)


def _paths():
    """Return (data_dir, overrides_path) from app config."""
    data_dir = current_app.config.get("AD_DATA_DIR", "")
    overrides = os.path.join(data_dir, "AD_Compliance_Overrides.json")
    return data_dir, overrides


# ── Main page ──────────────────────────────────────────────────────

@ad_bp.route("/")
@ad_bp.route("/dashboard")
@module_required('report_ad')
def dashboard():
    return render_template("report_ad/dashboard.html", page="ad_dashboard")


# ── API — users list ───────────────────────────────────────────────

@ad_bp.route("/api/users")
@module_required('report_ad')
def api_users():
    data_dir, overrides_path = _paths()
    users = load_all_users(data_dir, overrides_path)
    return jsonify(users)


# ── API — stats ────────────────────────────────────────────────────

@ad_bp.route("/api/stats")
@module_required('report_ad')
def api_stats():
    data_dir, overrides_path = _paths()
    users = load_all_users(data_dir, overrides_path)
    return jsonify(calculate_stats(users))


# ── API — ingest (receives data from PS script) ────────────────────

@ad_bp.route("/api/ingest", methods=["POST"])
def api_ingest():
    token = request.headers.get("X-API-Key")
    expected = current_app.config.get("INGEST_TOKEN", "")
    if expected and token != expected:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data or "environment" not in data:
        return jsonify({"error": "JSON inválido ou campo 'environment' ausente"}), 400

    data_dir, _ = _paths()
    env_name = data["environment"].replace(" ", "_").lower()
    dest = os.path.join(data_dir, f"ad_users_report_{env_name}.json")
    write_json(dest, data)
    logger.info("Ingest: wrote %d users for environment '%s'", len(data.get("users", [])), env_name)
    return jsonify({"status": "success"})


# ── API — exceptions ───────────────────────────────────────────────

@ad_bp.route("/api/exceptions/<username>", methods=["POST"])
@module_required('report_ad')
def save_exception(username: str):
    body = request.get_json(silent=True) or {}
    reason = body.get("reason", "").strip()
    if not reason:
        return jsonify({"error": "Motivo obrigatório"}), 400

    _, overrides_path = _paths()
    from app.modules.report_ad.utils.data_manager import _read_json
    overrides = _read_json(overrides_path, default={})
    overrides[username.lower()] = {
        "username":        username,
        "reason":          reason,
        "date":            datetime.now().isoformat(),
        "approvedBy":      current_user.username,
        "approvalDate":    datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    write_json(overrides_path, overrides)
    return jsonify({"status": "success"})


@ad_bp.route("/api/exceptions/<username>", methods=["DELETE"])
@module_required('report_ad')
def remove_exception(username: str):
    _, overrides_path = _paths()
    from app.modules.report_ad.utils.data_manager import _read_json
    overrides = _read_json(overrides_path, default={})
    overrides.pop(username.lower(), None)
    write_json(overrides_path, overrides)
    return jsonify({"status": "success"})


# ── ISO/SOC page ───────────────────────────────────────────────────

@ad_bp.route("/iso-soc")
@module_required('report_ad')
def iso_soc():
    return render_template("report_ad/iso_soc.html", page="ad_iso_soc")


@ad_bp.route("/api/iso-soc")
@module_required('report_ad')
def api_iso_soc():
    data_dir, overrides_path = _paths()
    users = load_all_users(data_dir, overrides_path)
    return jsonify(calculate_iso_soc_compliance(users))


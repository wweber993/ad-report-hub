"""
AD Report Hub — Report AD Module Routes
"""

import logging
import os
import threading
from datetime import datetime
from functools import wraps

import requests as http_requests
from flask import current_app, jsonify, render_template, request, session
from flask_login import current_user, login_required

from app import cache
from app.models import log_audit
from app.utils import module_required
from app.modules.report_ad import ad_bp
from app.modules.report_ad.utils.data_manager import (
    calculate_iso_soc_compliance,
    calculate_stats,
    load_all_users,
    load_history_snapshots,
    write_json,
    write_snapshot,
    purge_old_snapshots,
)

logger = logging.getLogger(__name__)


def _csrf_valid() -> bool:
    """Validate CSRF token from header or form against the session token."""
    token = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
        or ""
    )
    return token == session.get("csrf_token", "")


def csrf_protected(f):
    """Decorator: reject non-GET requests with invalid CSRF token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _csrf_valid():
            logger.warning("CSRF validation failed for %s %s from %s",
                           request.method, request.path, request.remote_addr)
            return jsonify({"error": "CSRF token inválido ou ausente."}), 403
        return f(*args, **kwargs)
    return decorated


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
    users = _load_users_cached(data_dir, overrides_path)
    return jsonify(users)


# ── API — stats ────────────────────────────────────────────────────────

@ad_bp.route("/api/stats")
@module_required('report_ad')
def api_stats():
    data_dir, overrides_path = _paths()
    users = _load_users_cached(data_dir, overrides_path)
    return jsonify(calculate_stats(users))


# ── API — ingest (receives data from PS script) ────────────────────

@ad_bp.route("/api/ingest", methods=["POST"])
def api_ingest():
    token = request.headers.get("X-API-Key", "")
    expected = current_app.config.get("INGEST_TOKEN", "")
    if not expected:
        logger.warning("INGEST_TOKEN not configured — rejecting request for security. Set INGEST_TOKEN in .env")
        return jsonify({"error": "Server misconfigured: INGEST_TOKEN not set"}), 503
    if token != expected:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data or "environment" not in data:
        return jsonify({"error": "JSON inválido ou campo 'environment' ausente"}), 400

    data_dir, overrides_path = _paths()
    env_name  = data["environment"].replace(" ", "_").lower()
    env_label = data.get("environment", env_name)
    dest      = os.path.join(data_dir, f"ad_users_report_{env_name}.json")
    write_json(dest, data)

    # Invalidate the user cache so next request re-loads fresh data
    cache.delete_memoized(_load_users_cached)

    # Compute stats and compliance for snapshot + alerting
    users      = load_all_users(data_dir, overrides_path)
    stats      = calculate_stats(users)
    compliance = calculate_iso_soc_compliance(users)
    comp_summary = compliance.get("summary", {})

    # Write compact snapshot (async to not slow down ingest response)
    retention = current_app.config.get("SNAPSHOT_RETENTION_DAYS", 90)
    def _write_snap():
        write_snapshot(data_dir, env_label, stats, comp_summary)
        purge_old_snapshots(data_dir, retention)
    threading.Thread(target=_write_snap, daemon=True).start()

    # Send webhook alerts if thresholds breached
    webhook_url = current_app.config.get("WEBHOOK_URL", "")
    if webhook_url:
        _maybe_send_webhook(current_app._get_current_object(), webhook_url, env_label, stats, comp_summary)

    n_users = len(data.get("users", []))
    logger.info("Ingest OK: %d users for env '%s'", n_users, env_label)
    return jsonify({"status": "success", "users_imported": n_users,
                    "healthScore": stats.get("healthScore", 0)})


# ── API — exceptions ───────────────────────────────────────────────

@ad_bp.route("/api/exceptions/<username>", methods=["POST"])
@module_required('report_ad')
@csrf_protected
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
    cache.delete_memoized(_load_users_cached)
    log_audit(current_user.username, "AD_EXCEPTION_ADDED", target=username, details=f"Motivo: {reason}")
    return jsonify({"status": "success"})


@ad_bp.route("/api/exceptions/<username>", methods=["DELETE"])
@module_required('report_ad')
@csrf_protected
def remove_exception(username: str):
    _, overrides_path = _paths()
    from app.modules.report_ad.utils.data_manager import _read_json
    overrides = _read_json(overrides_path, default={})
    overrides.pop(username.lower(), None)
    write_json(overrides_path, overrides)
    cache.delete_memoized(_load_users_cached)
    log_audit(current_user.username, "AD_EXCEPTION_REMOVED", target=username)
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
    users = _load_users_cached(data_dir, overrides_path)
    return jsonify(calculate_iso_soc_compliance(users))


# ── History page ───────────────────────────────────────────────────────

@ad_bp.route("/history")
@module_required('report_ad')
def history():
    return render_template("report_ad/history.html", page="ad_history")


@ad_bp.route("/api/history")
@module_required('report_ad')
def api_history():
    data_dir, overrides_path = _paths()
    env  = request.args.get("env", None)
    days = int(request.args.get("days", 30))
    days = min(max(days, 1), 365)  # clamp 1–1 year

    snapshots = load_history_snapshots(data_dir, environment=env, days=days)

    # Return available environments for the filter dropdown
    users = _load_users_cached(data_dir, overrides_path)
    stats = calculate_stats(users)
    envs  = stats.get("environments", [])

    return jsonify({"snapshots": snapshots, "environments": envs})


# ── Cached loader (shared by all API routes) ────────────────────────────

# Removed cache.memoize per user request to always load fresh data
def _load_users_cached(data_dir: str, overrides_path: str) -> list:
    """Cached wrapper around load_all_users. TTL = 5 minutes."""
    import time
    t0 = time.perf_counter()
    users = load_all_users(data_dir, overrides_path)
    elapsed = time.perf_counter() - t0
    logger.info("[Disk Load] Carregou %d usuários diretamente do arquivo JSON em %.3fs", len(users), elapsed)
    return users


# ── Webhook / Alert sender ────────────────────────────────────────────────

def _maybe_send_webhook(app, webhook_url: str, env: str, stats: dict, comp_summary: dict):
    """
    Evaluate alert thresholds and POST a webhook payload if any is breached.
    Runs in a daemon thread — does not block the ingest response.
    """
    health_threshold      = app.config.get("ALERT_HEALTH_THRESHOLD", 60)
    locked_threshold      = app.config.get("ALERT_LOCKED_THRESHOLD", 0)
    noncompliant_pct_thr  = app.config.get("ALERT_NONCOMPLIANT_PCT", 30)

    health         = stats.get("healthScore", 100)
    locked         = stats.get("lockedOut", 0)
    total          = stats.get("total", 1) or 1
    non_compliant  = stats.get("nonCompliant", 0)
    noncompliant_pct = round(non_compliant / total * 100)

    alerts = []
    if health < health_threshold:
        alerts.append({"type": "LOW_HEALTH_SCORE",
                       "message": f"Health Score caiu para {health}% (limite: {health_threshold}%)",
                       "value": health})
    if locked > locked_threshold:
        alerts.append({"type": "LOCKED_ACCOUNTS",
                       "message": f"{locked} conta(s) bloqueada(s) detectada(s)",
                       "value": locked})
    if noncompliant_pct > noncompliant_pct_thr:
        alerts.append({"type": "HIGH_NONCOMPLIANCE",
                       "message": f"{noncompliant_pct}% dos usuários não conforme (limite: {noncompliant_pct_thr}%)",
                       "value": noncompliant_pct})

    if not alerts:
        return

    payload = {
        "source":      "AD Report Hub",
        "environment": env,
        "timestamp":   datetime.now().isoformat(),
        "healthScore": health,
        "alerts":      alerts,
        "stats":       stats,
        "compliance":  comp_summary,
    }

    def _send():
        try:
            resp = http_requests.post(webhook_url, json=payload, timeout=10)
            logger.info("Webhook sent to %s — status %d", webhook_url, resp.status_code)
        except Exception as exc:
            logger.warning("Webhook delivery failed: %s", exc)

    threading.Thread(target=_send, daemon=True).start()

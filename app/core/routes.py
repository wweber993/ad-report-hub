"""
AD Report Hub — Core Routes (home, health)
"""

from flask import redirect, render_template, url_for
from flask_login import current_user, login_required

from app.core import core_bp


@core_bp.route("/")
def index():
    return redirect(url_for("ad.dashboard"))


@core_bp.route("/home")
@login_required
def home():
    return redirect(url_for("ad.dashboard"))


@core_bp.route("/health")
def health():
    from flask import jsonify
    return jsonify({"status": "ok", "app": "AD Report Hub"})

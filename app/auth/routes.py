"""
CyberHub — Auth Routes
  /login, /logout, /mfa, /change-password
"""

import logging
import os
import random
import string
from datetime import datetime

import qrcode
import base64
from io import BytesIO

from flask import (
    flash, redirect, render_template, request, session, url_for
)
from flask_login import current_user, login_required, login_user, logout_user

from app.auth    import auth_bp
from app.models  import User, db

logger = logging.getLogger(__name__)

# ── Rate limiter (simple in-memory) ────────────────────────────────
from datetime import timedelta
_rate_limits: dict = {}

def _check_rate_limit(key: str, limit: int = 10, window: int = 60) -> bool:
    """Returns True if request is allowed, False if rate-limited."""
    now = datetime.utcnow()
    _rate_limits.setdefault(key, [])
    _rate_limits[key] = [t for t in _rate_limits[key] if t > now - timedelta(seconds=window)]
    if len(_rate_limits[key]) >= limit:
        return False
    _rate_limits[key].append(now)
    return True


# ── Login ──────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("core.home"))

    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if not _check_rate_limit(f"login:{ip}"):
            flash("Muitas tentativas. Tente novamente em alguns minutos.", "danger")
            return redirect(url_for("auth.login"))

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            logger.warning("Failed login attempt for '%s' from %s", username, ip)
            flash("Usuário ou senha inválidos.", "danger")
            if user:
                user.failed_attempts = (user.failed_attempts or 0) + 1
                if user.failed_attempts >= 5:
                    user.is_locked = True
                    logger.warning("Account '%s' locked after 5 failed attempts.", username)
                db.session.commit()
            return redirect(url_for("auth.login"))

        if user.is_locked:
            flash("Conta bloqueada. Entre em contato com o administrador.", "danger")
            return redirect(url_for("auth.login"))

        # Reset failed attempts
        user.failed_attempts = 0
        db.session.commit()

        # Send to MFA or Setup MFA
        session["mfa_user_id"] = user.id
        
        if user.totp_enabled:
            return redirect(url_for("auth.mfa"))
        else:
            return redirect(url_for("auth.setup_mfa"))

    return render_template("auth/login.html")


# ── MFA ────────────────────────────────────────────────────────────

@auth_bp.route("/mfa", methods=["GET", "POST"])
def mfa():
    user_id = session.get("mfa_user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    user = db.session.get(User, user_id)
    if not user or not user.totp_enabled:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if user.is_totp_valid(code):
            login_user(user, remember=False)
            user.last_login = datetime.utcnow()
            db.session.commit()
            session.pop("mfa_user_id", None)
            logger.info("User '%s' logged in successfully.", user.username)
            return redirect(url_for("core.home"))
        else:
            flash("Código inválido.", "danger")

    return render_template("auth/mfa.html")


# ── Setup MFA ──────────────────────────────────────────────────────

@auth_bp.route("/setup-mfa", methods=["GET", "POST"])
def setup_mfa():
    user_id = session.get("mfa_user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    user = db.session.get(User, user_id)
    if not user:
        return redirect(url_for("auth.login"))

    if user.totp_enabled:
        return redirect(url_for("auth.mfa"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if user.is_totp_valid(code):
            user.totp_enabled = True
            db.session.commit()
            
            login_user(user, remember=False)
            user.last_login = datetime.utcnow()
            db.session.commit()
            session.pop("mfa_user_id", None)
            logger.info("User '%s' setup MFA and logged in successfully.", user.username)
            flash("Autenticação em duas etapas configurada com sucesso!", "success")
            return redirect(url_for("core.home"))
        else:
            flash("Código inválido. Tente novamente.", "danger")

    # Ensure user has a secret
    if not user.totp_secret:
        user.generate_totp_secret()
        
    uri = user.get_totp_uri()
    
    # Generate QR Code image in base64
    img = qrcode.make(uri)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    qr_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return render_template("auth/setup_mfa.html", qr_b64=qr_b64, secret=user.totp_secret)


# ── Logout ─────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    logger.info("User '%s' logged out.", current_user.username)
    logout_user()
    flash("Sessão encerrada com sucesso.", "info")
    return redirect(url_for("auth.login"))


# ── Change Password ────────────────────────────────────────────────

@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old_pw  = request.form.get("old_password", "")
        new_pw  = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if not current_user.check_password(old_pw):
            flash("Senha atual incorreta.", "danger")
            return redirect(url_for("auth.change_password"))

        if len(new_pw) < 8:
            flash("A nova senha deve ter pelo menos 8 caracteres.", "danger")
            return redirect(url_for("auth.change_password"))

        if new_pw != confirm:
            flash("As senhas não coincidem.", "danger")
            return redirect(url_for("auth.change_password"))

        current_user.set_password(new_pw)
        db.session.commit()
        logger.info("User '%s' changed password.", current_user.username)
        flash("Senha alterada com sucesso!", "success")
        return redirect(url_for("core.home"))

    return render_template("auth/change_password.html")




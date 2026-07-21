"""
AD Report Hub — Admin Routes
  /admin/users      (list, create, edit, delete, reset-password, reset-mfa)
"""

import logging
import random
import string
from functools import wraps

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.admin  import admin_bp
from app.models import User, AuditLog, ALL_MODULES, db, log_audit

logger = logging.getLogger(__name__)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash("Acesso restrito a administradores.", "danger")
            return redirect(url_for("core.home"))
        return f(*args, **kwargs)
    return decorated


def _random_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-="
    return "".join(random.choice(chars) for _ in range(length))


# ── User list ──────────────────────────────────────────────────────

@admin_bp.route("/users")
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users, all_modules=ALL_MODULES)


# ── Create user ────────────────────────────────────────────────────

@admin_bp.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    email    = request.form.get("email", "").strip()
    is_admin = request.form.get("is_admin") == "on"

    if not username or not email:
        flash("Usuário e e-mail são obrigatórios.", "danger")
        return redirect(url_for("admin.users"))

    if User.query.filter_by(username=username).first():
        flash(f"Usuário '{username}' já existe.", "danger")
        return redirect(url_for("admin.users"))

    if User.query.filter_by(email=email).first():
        flash(f"E-mail '{email}' já está em uso.", "danger")
        return redirect(url_for("admin.users"))

    password = _random_password()
    user = User(username=username, email=email, is_admin=is_admin)
    user.set_password(password)

    # Module permissions (ignored for admins, but stored anyway)
    selected_modules = request.form.getlist("modules")
    if selected_modules:
        user.set_modules(selected_modules)
    # else: NULL → full access

    db.session.add(user)
    db.session.commit()

    logger.info("Admin '%s' created user '%s'.", current_user.username, username)
    log_audit(current_user.username, "USER_CREATED", target=username, details=f"Admin: {is_admin}, Email: {email}")
    flash(
        f"✓ Usuário '{username}' criado com sucesso. "
        f"Senha temporária: {password} — "
        "Anote e envie ao usuário por canal seguro. "
        "Ele deverá trocar no primeiro acesso.",
        "warning",
    )
    return redirect(url_for("admin.users"))


# ── Edit user ──────────────────────────────────────────────────────

@admin_bp.route("/users/<int:uid>/edit", methods=["POST"])
@admin_required
def edit_user(uid: int):
    user     = db.get_or_404(User, uid)
    username = request.form.get("username", "").strip()
    email    = request.form.get("email", "").strip()

    if not username or not email:
        flash("Usuário e e-mail são obrigatórios.", "danger")
        return redirect(url_for("admin.users"))

    conflict_user  = User.query.filter(User.username == username, User.id != uid).first()
    conflict_email = User.query.filter(User.email == email,       User.id != uid).first()

    if conflict_user:
        flash(f"Usuário '{username}' já pertence a outra conta.", "danger")
        return redirect(url_for("admin.users"))
    if conflict_email:
        flash(f"E-mail '{email}' já está em uso por outra conta.", "danger")
        return redirect(url_for("admin.users"))

    user.username = username
    user.email    = email

    # Update module permissions
    selected_modules = request.form.getlist("modules")
    user.set_modules(selected_modules)  # empty list → NULL → full access

    db.session.commit()
    logger.info("Admin '%s' edited user id=%d → %s / %s",
                current_user.username, uid, username, email)
    log_audit(current_user.username, "USER_EDITED", target=username, details=f"Módulos atualizados: {selected_modules}")
    flash(f"Usuário '{username}' atualizado com sucesso.", "success")
    return redirect(url_for("admin.users"))


# ── Set module permissions ─────────────────────────────────────────

@admin_bp.route("/users/<int:uid>/modules", methods=["POST"])
@admin_required
def set_modules(uid: int):
    user = db.get_or_404(User, uid)
    selected = request.form.getlist("modules")
    user.set_modules(selected)
    db.session.commit()
    logger.info("Admin '%s' updated modules for user '%s': %s",
                current_user.username, user.username, selected)
    return jsonify({"ok": True, "modules": user.get_modules()})


# ── Toggle admin ───────────────────────────────────────────────────

@admin_bp.route("/users/<int:uid>/toggle-admin", methods=["POST"])
@admin_required
def toggle_admin(uid: int):
    user = db.get_or_404(User, uid)
    if user.id == current_user.id:
        return jsonify({"error": "Você não pode alterar seu próprio nível de acesso."}), 400
    user.is_admin = not user.is_admin
    db.session.commit()
    log_audit(current_user.username, "USER_TOGGLED_ADMIN", target=user.username, details=f"Tornado Admin: {user.is_admin}")
    return jsonify({"is_admin": user.is_admin, "is_locked": user.is_locked, "role": user.role_label})


# ── Reset password ─────────────────────────────────────────────────

@admin_bp.route("/users/<int:uid>/reset-password", methods=["POST"])
@admin_required
def reset_password(uid: int):
    user = db.get_or_404(User, uid)
    password = _random_password()
    user.set_password(password)
    user.is_locked = False
    user.failed_attempts = 0
    db.session.commit()

    logger.info("Admin '%s' reset password for user '%s'.", current_user.username, user.username)
    log_audit(current_user.username, "USER_RESET_PASSWORD", target=user.username)
    flash(
        f"✓ Senha de '{user.username}' redefinida. "
        f"Nova senha temporária: {password} — "
        "Envie ao usuário por canal seguro e peça para trocar no próximo acesso.",
        "warning",
    )
    return redirect(url_for("admin.users"))


# ── Reset MFA ──────────────────────────────────────────────────────

@admin_bp.route("/users/<int:uid>/reset-mfa", methods=["POST"])
@admin_required
def reset_mfa(uid: int):
    user = db.get_or_404(User, uid)
    if user.id == current_user.id:
        return jsonify({"error": "Você não pode redefinir seu próprio MFA por aqui."}), 400
    user.totp_secret  = None
    user.totp_enabled = False
    db.session.commit()
    logger.info("Admin '%s' reset MFA for user '%s'.", current_user.username, user.username)
    log_audit(current_user.username, "USER_RESET_MFA", target=user.username)
    return jsonify({
        "ok": True,
        "message": f"MFA de '{user.username}' redefinido. O usuário deverá configurar o Autenticador no próximo login."
    })


# ── Unlock account ─────────────────────────────────────────────────

@admin_bp.route("/users/<int:uid>/unlock", methods=["POST"])
@admin_required
def unlock_user(uid: int):
    user = db.get_or_404(User, uid)
    user.is_locked = False
    user.failed_attempts = 0
    db.session.commit()
    logger.info("Admin '%s' unlocked user '%s'.", current_user.username, user.username)
    log_audit(current_user.username, "USER_UNLOCKED", target=user.username)
    return jsonify({"ok": True, "username": user.username})


# ── Delete user ────────────────────────────────────────────────────

@admin_bp.route("/users/<int:uid>/delete", methods=["POST"])
@admin_required
def delete_user(uid: int):
    user = db.get_or_404(User, uid)
    if user.id == current_user.id:
        flash("Você não pode excluir sua própria conta.", "danger")
        return redirect(url_for("admin.users"))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    logger.info("Admin '%s' deleted user '%s'.", current_user.username, username)
    log_audit(current_user.username, "USER_DELETED", target=username)
    flash(f"Usuário '{username}' excluído com sucesso.", "success")
    return redirect(url_for("admin.users"))


# ── Audit Log ──────────────────────────────────────────────────────

@admin_bp.route("/audit")
@admin_required
def audit():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    return render_template("admin/audit.html", logs=logs, page="admin_audit")

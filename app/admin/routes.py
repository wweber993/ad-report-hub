"""
CyberHub — Admin Routes
  /admin/users      (list, create, edit, delete, reset-password)
"""

import logging
import random
import string
from functools import wraps

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_mail import Message

from app.admin  import admin_bp
from app.models import User, ALL_MODULES, db
from app        import mail

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

    try:
        _send_welcome_email(user, password)
        flash(f"Usuário '{username}' criado. Credenciais enviadas por e-mail.", "success")
    except Exception as exc:
        logger.error("Failed to send welcome email: %s", exc)
        flash(
            f"Usuário '{username}' criado. Senha temporária: {password} "
            "(e-mail indisponível — anote a senha!)",
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

    try:
        _send_reset_email(user, password)
        flash(f"Senha de '{user.username}' redefinida. Nova senha enviada por e-mail.", "success")
    except Exception as exc:
        logger.error("Failed to send reset email: %s", exc)
        flash(
            f"Senha redefinida. Nova senha: {password} "
            "(e-mail indisponível — anote a senha!)",
            "warning",
        )

    return redirect(url_for("admin.users"))


# ── Unlock account ─────────────────────────────────────────────────

@admin_bp.route("/users/<int:uid>/unlock", methods=["POST"])
@admin_required
def unlock_user(uid: int):
    user = db.get_or_404(User, uid)
    user.is_locked = False
    user.failed_attempts = 0
    db.session.commit()
    logger.info("Admin '%s' unlocked user '%s'.", current_user.username, user.username)
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
    flash(f"Usuário '{username}' excluído com sucesso.", "success")
    return redirect(url_for("admin.users"))


# ── Email helpers ──────────────────────────────────────────────────

def _send_welcome_email(user: User, password: str) -> None:
    msg = Message(
        subject="Bem-vindo ao AD Report Hub — Seus Dados de Acesso",
        recipients=[user.email],
    )
    msg.html = _access_email_html(user.username, password, is_reset=False)
    mail.send(msg)


def _send_reset_email(user: User, password: str) -> None:
    msg = Message(
        subject="AD Report Hub — Reset de Senha",
        recipients=[user.email],
    )
    msg.html = _access_email_html(user.username, password, is_reset=True)
    mail.send(msg)


def _access_email_html(username: str, password: str, is_reset: bool = False) -> str:
    if is_reset:
        subject_line  = "Redefinição de Senha"
        headline      = "Sua senha foi redefinida"
        body_intro    = "Um administrador redefiniu a senha da sua conta no AD Report Hub."
        icon          = "🔑"
        header_color  = "#1e1b4b"
        badge_color   = "#4f46e5"
        badge_label   = "Reset de Senha"
    else:
        subject_line  = "Bem-vindo ao AD Report Hub"
        headline      = "Sua conta foi criada"
        body_intro    = "Você recebeu acesso à plataforma AD Report Hub."
        icon          = "🛡️"
        header_color  = "#0f172a"
        badge_color   = "#0284c7"
        badge_label   = "Novo Acesso"

    return f"""<!DOCTYPE html>
<html lang="pt-BR" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<!--[if mso]>
<xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml>
<![endif]-->
<title>AD Report Hub &mdash; {subject_line}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:Segoe UI,Arial,sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
       style="background-color:#f1f5f9;">
  <tr>
    <td align="center" style="padding:40px 16px;">

      <!-- Card -->
      <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0"
             style="background-color:#ffffff;border-radius:12px;overflow:hidden;
                    border:1px solid #e2e8f0;max-width:560px;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background-color:{header_color};padding:28px 40px;text-align:center;">
            <span style="display:inline-block;background-color:{badge_color};
                         border-radius:8px;padding:8px 14px;margin-bottom:14px;
                         font-size:22px;">{icon}</span>
            <br>
            <span style="font-size:22px;font-weight:700;color:#f8fafc;
                         font-family:Segoe UI,Arial,sans-serif;">AD Report Hub</span>
            <br>
            <span style="display:inline-block;margin-top:8px;background-color:{badge_color};
                         color:#ffffff;font-size:11px;font-weight:700;
                         letter-spacing:0.8px;text-transform:uppercase;
                         padding:4px 12px;border-radius:20px;
                         font-family:Segoe UI,Arial,sans-serif;">{badge_label}</span>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:36px 40px 28px;">
            <h2 style="margin:0 0 8px;font-size:20px;font-weight:700;color:#0f172a;
                       font-family:Segoe UI,Arial,sans-serif;">{headline}</h2>
            <p style="margin:0 0 28px;font-size:14px;color:#475569;line-height:1.6;
                       font-family:Segoe UI,Arial,sans-serif;">
              Olá <strong>{username}</strong>, {body_intro}
            </p>

            <!-- Credentials table -->
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                   style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;
                          margin-bottom:24px;">
              <tr>
                <td style="padding:10px 16px;background-color:#f8fafc;
                           border-bottom:1px solid #e2e8f0;" colspan="2">
                  <span style="font-size:11px;font-weight:700;color:#64748b;
                               text-transform:uppercase;letter-spacing:0.6px;
                               font-family:Segoe UI,Arial,sans-serif;">CREDENCIAIS DE ACESSO</span>
                </td>
              </tr>
              <tr>
                <td style="padding:14px 16px;width:120px;border-bottom:1px solid #f1f5f9;">
                  <span style="font-size:13px;color:#64748b;
                               font-family:Segoe UI,Arial,sans-serif;">Usuário</span>
                </td>
                <td style="padding:14px 16px;border-bottom:1px solid #f1f5f9;">
                  <span style="font-size:14px;font-weight:600;color:#0f172a;
                               font-family:Segoe UI,Arial,sans-serif;">{username}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:14px 16px;width:120px;background-color:#fafafa;">
                  <span style="font-size:13px;color:#64748b;
                               font-family:Segoe UI,Arial,sans-serif;">Senha</span>
                </td>
                <td style="padding:14px 16px;background-color:#fafafa;">
                  <span style="font-size:15px;font-weight:700;color:#1d4ed8;
                               letter-spacing:2px;font-family:'Courier New',Courier,monospace;">{password}</span>
                </td>
              </tr>
            </table>

            <!-- Warning box -->
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                   style="margin-bottom:24px;">
              <tr>
                <td style="background-color:#eff6ff;border-left:4px solid #3b82f6;
                           border-radius:6px;padding:14px 18px;">
                  <p style="margin:0;font-size:13px;color:#1e40af;
                             font-family:Segoe UI,Arial,sans-serif;">
                    🔒 &nbsp;Por segurança, <strong>altere sua senha no primeiro acesso</strong>:
                    Menu &rarr; Alterar Senha.
                  </p>
                </td>
              </tr>
            </table>

            <p style="margin:0;font-size:13px;color:#94a3b8;line-height:1.5;
                       font-family:Segoe UI,Arial,sans-serif;">
              Se você não solicitou este acesso, entre em contato com o administrador imediatamente.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background-color:#f8fafc;border-top:1px solid #e2e8f0;
                     padding:18px 40px;text-align:center;">
            <p style="margin:0;font-size:12px;color:#94a3b8;
                       font-family:Segoe UI,Arial,sans-serif;">
              AD Report Hub &mdash; Active Directory Analytics &nbsp;|&nbsp;
              Este é um e-mail automático, não responda.
            </p>
          </td>
        </tr>

      </table>
      <!-- /Card -->

    </td>
  </tr>
</table>
</body>
</html>"""


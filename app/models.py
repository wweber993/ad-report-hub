"""
CyberHub — Unified User Model
"""

import json
import random
import string
from datetime import datetime, timedelta
from typing import List

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Catalogue of all available modules — slug: display label
ALL_MODULES = {
    "report_ad":       "Report AD",
}


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(80),  unique=True, nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    password_hash  = db.Column(db.String(256))
    is_admin       = db.Column(db.Boolean, default=False)

    # Module access — JSON-encoded list of module slugs, e.g. '["report_vulns","report_ad"]'
    # NULL / empty means access to ALL modules (backward-compatible for existing users)
    modules_json   = db.Column(db.Text, nullable=True, default=None)

    # MFA
    totp_secret    = db.Column(db.String(32), nullable=True)
    totp_enabled   = db.Column(db.Boolean, default=False)

    # Security tracking
    last_login     = db.Column(db.DateTime)
    failed_attempts = db.Column(db.Integer, default=0)
    is_locked      = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    # ── Module access helpers ──────────────────────────────────────

    def get_modules(self) -> List[str]:
        """Return list of allowed module slugs.
        Admins and users with NULL modules_json have access to everything."""
        if self.is_admin or not self.modules_json:
            return list(ALL_MODULES.keys())
        try:
            return json.loads(self.modules_json)
        except (ValueError, TypeError):
            return list(ALL_MODULES.keys())

    def set_modules(self, slugs: List[str]) -> None:
        """Persist the list of allowed module slugs."""
        self.modules_json = json.dumps([s for s in slugs if s in ALL_MODULES])

    def has_module(self, slug: str) -> bool:
        """Return True if the user is allowed to access the given module."""
        if self.is_admin:
            return True
        mods = self.get_modules()
        return slug in mods

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def generate_totp_secret(self) -> str:
        import pyotp
        self.totp_secret = pyotp.random_base32()
        db.session.commit()
        return self.totp_secret

    def get_totp_uri(self) -> str:
        import pyotp
        if not self.totp_secret:
            return None
        return pyotp.totp.TOTP(self.totp_secret).provisioning_uri(
            name=self.email, issuer_name="AD Report Hub"
        )

    def is_totp_valid(self, code: str) -> bool:
        import pyotp
        if not self.totp_secret:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(code)

    @property
    def role_label(self) -> str:
        return "Administrador" if self.is_admin else "Analista"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username}>"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id        = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    username  = db.Column(db.String(80), nullable=False, index=True)
    action    = db.Column(db.String(120), nullable=False)
    target    = db.Column(db.String(120), nullable=True)
    details   = db.Column(db.Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.timestamp} {self.username} {self.action}>"


def log_audit(username: str, action: str, target: str = None, details: str = None):
    """
    Helper function to record an action in the audit log.
    If there is no database session available or it fails, logs to python logger.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        entry = AuditLog(
            username=username,
            action=action,
            target=target,
            details=details
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("Failed to write to AuditLog: %s (action=%s, target=%s)", exc, action, target)

"""
CyberHub — Shared utilities and decorators
"""

from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user, login_required


def module_required(slug: str):
    """Decorator that ensures the current user has access to a module.

    Usage:
        @module_required('report_vulns')
        def my_view(): ...

    Admins always pass. For regular users, checks User.has_module(slug).
    Implies @login_required — no need to stack both decorators.
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.has_module(slug):
                flash("Você não tem acesso a este módulo.", "danger")
                return redirect(url_for("core.home"))
            return f(*args, **kwargs)
        return wrapped
    return decorator

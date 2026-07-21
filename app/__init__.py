"""
AD Report Hub — Application Factory
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask
from flask_login import LoginManager
from flask_caching import Cache
from flask_migrate import Migrate

from app.config import Config
from app.models import db, User

login_manager = LoginManager()
cache = Cache()
migrate = Migrate()


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_object(Config)

    # ── Logging ────────────────────────────────────────────────────
    _setup_logging(app)

    # ── Extensions ─────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    cache.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Por favor, faça login para continuar."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ── Security headers ───────────────────────────────────────────
    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "img-src * data:; font-src * data:; frame-src *;"
        )
        return response

    # ── CSRF token injection ───────────────────────────────────────
    from flask import session

    @app.context_processor
    def inject_csrf():
        if "csrf_token" not in session:
            session["csrf_token"] = os.urandom(24).hex()
        return dict(csrf_token=session.get("csrf_token", ""))

    # ── Create DB Directory ─────────────────────────────────────────
    with app.app_context():
        os.makedirs(Config.DATA_DIR, exist_ok=True)

    # ── Blueprints ─────────────────────────────────────────────────
    from app.auth.routes    import auth_bp
    from app.admin.routes   import admin_bp
    from app.core.routes    import core_bp
    from app.modules.report_ad.routes       import ad_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp,    url_prefix="/admin")
    app.register_blueprint(core_bp)
    app.register_blueprint(ad_bp,       url_prefix="/ad")

    return app


def _setup_logging(app: Flask) -> None:
    os.makedirs(Config.LOG_DIR, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, Config.LOG_LEVEL, logging.INFO))

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)

    fh = RotatingFileHandler(
        Config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

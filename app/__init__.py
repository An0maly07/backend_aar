"""Women Safety System - backend application factory."""
import logging
import os
from collections import deque
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # must run before app.config reads the environment

from flask import Flask, request  # noqa: E402

from app.config import CONFIGS  # noqa: E402
from app.errors import error_response, register_error_handlers  # noqa: E402
from app.extensions import cors, db, limiter, login_manager, migrate  # noqa: E402

_MUTATING_METHODS = {"POST", "PUT", "PATCH"}


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    config_name = config_name or os.getenv("APP_ENV", "development")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(CONFIGS[config_name])
    app.config.update(overrides or {})

    if config_name == "production" and app.config["SECRET_KEY"] == "dev-only-insecure-key":
        raise RuntimeError("Set a strong SECRET_KEY before running in production.")

    _configure_logging(app)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    from app import models  # noqa: F401  (register tables for Flask-Migrate)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # SQLite needs batch mode for ALTERs
    limiter.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGINS"]}},
                  supports_credentials=True)
    _configure_login(app)

    from app.api import register_blueprints
    from app.cli import register_cli
    from app.services.risk.scorer import RiskScorer

    register_blueprints(app)
    register_error_handlers(app)
    register_cli(app)
    _register_request_hooks(app)

    app.extensions["risk_scorer"] = RiskScorer.load(app.config["RISK_MODEL_PATH"])
    app.extensions["alert_outbox"] = deque(maxlen=200)  # console-channel alerts, for dev/tests
    return app


def _configure_logging(app: Flask) -> None:
    logging.basicConfig(
        level=app.config["LOG_LEVEL"],
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def _configure_login(app: Flask) -> None:
    from app.models import User

    login_manager.init_app(app)
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        return error_response(401, "unauthorized", "Please log in to continue.")


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def require_json_for_writes():
        # CSRF defence for a cookie-session JSON API: HTML forms can't send
        # application/json cross-site, and SameSite cookies cover the rest.
        if request.method in _MUTATING_METHODS and request.path.startswith("/api/") and not request.is_json:
            return error_response(415, "unsupported_media_type", "Send requests with Content-Type: application/json.")
        return None

    if app.config["ENABLE_SWEEPER"]:
        @app.before_request
        def start_background_sweeper():
            # Started lazily so only processes that serve traffic run it
            # (not `flask db upgrade`, and not the debug reloader's parent).
            from app.services.sweeper import start_sweeper
            start_sweeper(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        # Never leak the tracking token in the Referer header to third parties.
        response.headers.setdefault("Referrer-Policy", "strict-origin")
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

import os
import secrets
from datetime import timedelta

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.routes import register_routes
from core.async_tasks import LocalTaskRunner
from core.config import load_settings
from core.db import db_conn, init_db
from core.demo import assert_demo_safe, demo_live_enabled, demo_mode_enabled
from core.logging_setup import configure_logging
from core.task_service import TASK_HANDLERS
from core.users import ensure_admin_account


def _read_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _require_strong_secret_key() -> str:
    key = str(os.getenv("FLASK_SECRET_KEY", "")).strip()
    if len(key) < 32 or key in {"dev-insecure-change-me", "replace_with_strong_random_secret"}:
        raise RuntimeError("FLASK_SECRET_KEY must be set to a strong random value (>=32 chars).")
    return key


def create_app() -> Flask:
    """Create and configure Flask application instance."""
    configure_logging()
    settings = load_settings()
    demo_mode = demo_mode_enabled()
    if demo_mode:
        assert_demo_safe(settings)
    if demo_mode and not demo_live_enabled():
        # No sessions exist in the read-only demo (sign-in is refused), so an ephemeral key is enough: no secrets
        # needed. The live demo has guest sessions and needs a real key shared by all workers.
        secret_key = str(os.getenv("FLASK_SECRET_KEY", "")).strip() or secrets.token_urlsafe(48)
    else:
        secret_key = _require_strong_secret_key()
    init_db(settings.app.db_path)
    with db_conn(settings.app.db_path) as conn:
        ensure_admin_account(conn)

    app = Flask(__name__, static_folder=None)  # the web app is served by app/route_groups/spa.py
    app.secret_key = secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = _read_bool_env("SESSION_COOKIE_SECURE", False)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=14)
    # Includes base64 expansion for the 30 MiB aggregate attachment limit.
    app.config["MAX_CONTENT_LENGTH"] = 42 * 1024 * 1024
    app.config["DEMO_MODE"] = demo_mode
    app.extensions["task_runner"] = LocalTaskRunner(settings.app.db_path, handlers=TASK_HANDLERS)
    register_routes(app)
    trusted_proxy_hops = int(os.getenv("TRUSTED_PROXY_HOPS", "0") or 0)
    if trusted_proxy_hops > 0:
        # Only behind a reverse proxy that sets X-Forwarded-*; otherwise clients could spoof them.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_proxy_hops, x_proto=trusted_proxy_hops)  # type: ignore[method-assign]
    return app

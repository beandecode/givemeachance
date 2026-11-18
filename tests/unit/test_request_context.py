from flask import Flask, session

from core.config import load_settings
from core.db import db_conn, init_db
from core.request_context import (
    is_admin_user,
    profile_scope_user_id,
    quota_subject_for_user,
    resolve_request_user,
)
from core.users import create_user


def _build_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "test-secret"
    return app


def test_resolve_request_user_from_active_session_user():
    settings = load_settings()
    init_db(settings.app.db_path)

    with db_conn(settings.app.db_path) as conn:
        user = create_user(conn, username="session_user", password="password123")

    app = _build_app()
    with app.test_request_context("/"):
        session["user_id"] = int(user["id"])
        with db_conn(settings.app.db_path) as conn:
            resolved = resolve_request_user(conn, allow_demo_fallback=False)

    assert resolved is not None
    assert int(resolved["id"]) == int(user["id"])


def test_demo_user_is_resolved_only_in_demo_mode(monkeypatch):
    settings = load_settings()
    init_db(settings.app.db_path)

    app = _build_app()
    with app.test_request_context("/"):
        with db_conn(settings.app.db_path) as conn:
            assert resolve_request_user(conn, allow_demo_fallback=True) is None
        monkeypatch.setenv("DEMO_MODE", "true")
        with db_conn(settings.app.db_path) as conn:
            resolved = resolve_request_user(conn, allow_demo_fallback=True)

    assert resolved is not None
    assert str(resolved["username"]) == "demo"


def test_scope_and_quota_helpers():
    admin = {"id": 1, "is_admin": 1}
    normal = {"id": 22, "is_admin": 0}

    assert is_admin_user(admin) is True
    assert is_admin_user(normal) is False
    assert profile_scope_user_id(admin) == 1
    assert profile_scope_user_id(normal) == 22
    assert quota_subject_for_user(None) == "anonymous"
    assert quota_subject_for_user(normal) == "user:22"

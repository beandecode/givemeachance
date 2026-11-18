from app import create_app
from core.config import load_settings
from core.db import db_conn, migrations
from core.login_throttle import MAX_FAILURES
from core.users import authenticate_user, ensure_default_demo_user


def _client_with_user(username="hardening_user", password="password123"):
    app = create_app()
    client = app.test_client()
    assert client.post("/api/v1/account", json={"username": username, "password": password}).status_code == 201
    client.delete("/api/v1/session")
    return app, client


def test_repeated_failed_logins_lock_the_account_temporarily():
    _, client = _client_with_user()

    for _ in range(MAX_FAILURES):
        response = client.post("/api/v1/session", json={"username": "hardening_user", "password": "wrong-password"})
        assert response.status_code == 401

    locked = client.post("/api/v1/session", json={"username": "hardening_user", "password": "password123"})
    assert locked.status_code == 429
    other_user = client.post("/api/v1/session", json={"username": "someone_else", "password": "wrong-password"})
    assert other_user.status_code == 401


def test_successful_login_clears_failure_count():
    _, client = _client_with_user()
    for _ in range(MAX_FAILURES - 1):
        client.post("/api/v1/session", json={"username": "hardening_user", "password": "wrong-password"})

    assert (
        client.post("/api/v1/session", json={"username": "hardening_user", "password": "password123"}).status_code
        == 200
    )
    client.delete("/api/v1/session")
    for _ in range(MAX_FAILURES - 1):
        client.post("/api/v1/session", json={"username": "hardening_user", "password": "wrong-password"})
    assert (
        client.post("/api/v1/session", json={"username": "hardening_user", "password": "password123"}).status_code
        == 200
    )


def test_login_starts_a_fresh_permanent_session_and_logout_clears_it():
    _, client = _client_with_user()
    with client.session_transaction() as sess:
        sess["planted_by_attacker"] = "x"

    client.post("/api/v1/session", json={"username": "hardening_user", "password": "password123"})
    with client.session_transaction() as sess:
        assert "planted_by_attacker" not in sess
        assert sess.permanent

    client.delete("/api/v1/session")
    with client.session_transaction() as sess:
        assert dict(sess) == {}


def test_readiness_reports_pending_migrations(monkeypatch):
    app = create_app()
    client = app.test_client()
    assert client.get("/healthz").get_json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200

    monkeypatch.setattr(migrations, "MIGRATIONS", [*migrations.MIGRATIONS, ("9999_future", lambda conn: None)])
    import app.route_groups.system as system

    monkeypatch.setattr(system, "MIGRATIONS", migrations.MIGRATIONS)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.get_json()["pending_migrations"] == ["9999_future"]


def test_demo_account_has_no_public_password():
    create_app()
    with db_conn(load_settings().app.db_path) as conn:
        ensure_default_demo_user(conn)
        assert authenticate_user(conn, "demo", "demo12345") is None


def test_registration_is_closed_unless_explicitly_opened(monkeypatch):
    monkeypatch.delenv("REGISTRATION_MODE")
    client = create_app().test_client()

    response = client.post("/api/v1/account", json={"username": "newcomer", "password": "password123"})
    assert (response.status_code, response.get_json()["error_code"]) == (403, 1003)

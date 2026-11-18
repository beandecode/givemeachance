import threading

import pytest

from core.config import load_settings
from core.db import db_conn, init_db
from core.users import authenticate_user, create_user, ensure_admin_account, ensure_default_demo_user


def _db_path() -> str:
    settings = load_settings()
    init_db(settings.app.db_path)
    return settings.app.db_path


def _run_concurrently(db_path: str, func, workers: int = 4) -> list:
    barrier = threading.Barrier(workers)
    results: list = []
    errors: list = []

    def worker():
        try:
            barrier.wait()
            with db_conn(db_path) as conn:
                results.append(func(conn))
        except Exception as exc:  # collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    return results


def test_concurrent_demo_user_creation_does_not_fail():
    db_path = _db_path()

    rows = _run_concurrently(db_path, ensure_default_demo_user)

    assert len({int(row["id"]) for row in rows}) == 1


def test_create_user_rejects_duplicate_username():
    db_path = _db_path()
    with db_conn(db_path) as conn:
        create_user(conn, username="taken_name", password="password123")

    with db_conn(db_path) as conn, pytest.raises(ValueError, match="already exists"):
        create_user(conn, username="Taken_Name", password="password456")


def test_admin_bootstrap_creates_admin_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", "owner")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "bootstrap-pass-1")
    db_path = _db_path()

    rows = _run_concurrently(db_path, ensure_admin_account)

    assert {int(row["is_admin"]) for row in rows} == {1}
    with db_conn(db_path) as conn:
        assert authenticate_user(conn, "owner", "bootstrap-pass-1") is not None


def test_admin_bootstrap_does_not_promote_existing_non_admin_without_force_reset(monkeypatch):
    db_path = _db_path()
    with db_conn(db_path) as conn:
        create_user(conn, username="owner", password="squatter-pass")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", "owner")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "bootstrap-pass-1")

    with db_conn(db_path) as conn:
        row = ensure_admin_account(conn)

    assert int(row["is_admin"]) == 0
    with db_conn(db_path) as conn:
        assert authenticate_user(conn, "owner", "squatter-pass") is not None


def test_admin_bootstrap_force_reset_promotes_and_replaces_password(monkeypatch):
    db_path = _db_path()
    with db_conn(db_path) as conn:
        create_user(conn, username="owner", password="squatter-pass")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_USERNAME", "owner")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "bootstrap-pass-1")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_FORCE_RESET", "true")

    with db_conn(db_path) as conn:
        row = ensure_admin_account(conn)

    assert int(row["is_admin"]) == 1
    with db_conn(db_path) as conn:
        assert authenticate_user(conn, "owner", "squatter-pass") is None
        assert authenticate_user(conn, "owner", "bootstrap-pass-1") is not None

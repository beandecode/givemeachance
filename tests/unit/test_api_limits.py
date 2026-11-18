import pytest

from core.api_limits import consume_dual_api_quota, get_daily_api_usage_for_subject
from core.config import load_settings
from core.db import db_conn, init_db


def test_quota_consumed_between_caller_writes_is_kept_after_rollback():
    db_path = load_settings().app.db_path
    init_db(db_path)

    with pytest.raises(RuntimeError), db_conn(db_path) as conn:
        allowed, usage = consume_dual_api_quota(
            db_path, provider="gemini", subject="user:7", subject_daily_limit=5, global_daily_limit=10
        )
        assert allowed and usage["subject_used"] == 1
        conn.execute("INSERT INTO users (username, password_hash, created_at) VALUES ('after_call', 'x', 'now')")
        raise RuntimeError("persisting the provider result failed")

    summary = get_daily_api_usage_for_subject(db_path, "user:7", {"gemini": 5})
    assert summary[0]["used"] == 1


def test_quota_rejects_when_subject_limit_reached():
    db_path = load_settings().app.db_path
    init_db(db_path)

    for _ in range(2):
        allowed, _ = consume_dual_api_quota(
            db_path, provider="adzuna", subject="user:3", subject_daily_limit=2, global_daily_limit=10
        )
        assert allowed
    allowed, usage = consume_dual_api_quota(
        db_path, provider="adzuna", subject="user:3", subject_daily_limit=2, global_daily_limit=10
    )

    assert not allowed
    assert usage["reason"] == "subject_quota_reached"

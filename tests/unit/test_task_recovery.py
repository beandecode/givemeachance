import sqlite3
from datetime import timedelta

from core.async_tasks import (
    EXPIRED_MESSAGE,
    INTERRUPTED_MESSAGE,
    LocalTaskRunner,
    create_async_task,
    get_async_task,
    mark_task_cancelled,
    mark_task_running,
    mark_task_succeeded,
    recover_stale_tasks,
    request_cancel_task,
)
from core.config import load_settings
from core.db import db_conn, init_db
from core.errors import UserFacingError
from core.time_utils import utc_now
from core.users import create_user


def _db_with_user():
    db_path = load_settings().app.db_path
    init_db(db_path)
    with db_conn(db_path) as conn:
        user_id = int(create_user(conn, username="task_owner", password="password123")["id"])
    return db_path, user_id


def _new_task(conn, user_id, correlation_id="req_test"):
    return str(create_async_task(conn, "manual_search", user_id, {}, correlation_id)["task_id"])


def _events(conn, task_id):
    return [
        row[0] for row in conn.execute("SELECT event_type FROM task_events WHERE task_id = ? ORDER BY id", (task_id,))
    ]


def test_orphaned_running_and_unclaimed_queued_tasks_are_finished():
    db_path, user_id = _db_with_user()
    with db_conn(db_path) as conn:
        orphaned = _new_task(conn, user_id)
        mark_task_running(conn, orphaned)
        live = _new_task(conn, user_id)
        mark_task_running(conn, live)
        stale_queue = _new_task(conn, user_id)
        fresh_queue = _new_task(conn, user_id)
        long_ago = (utc_now() - timedelta(hours=2)).isoformat()
        conn.execute("UPDATE async_tasks SET heartbeat_at_utc = ? WHERE task_id = ?", (long_ago, orphaned))
        conn.execute("UPDATE async_tasks SET created_at_utc = ? WHERE task_id = ?", (long_ago, stale_queue))

    with db_conn(db_path) as conn:
        counts = recover_stale_tasks(
            conn, stale_running_after=timedelta(minutes=5), expire_queued_after=timedelta(minutes=30)
        )
        states = {task_id: get_async_task(conn, task_id) for task_id in (orphaned, live, stale_queue, fresh_queue)}

        assert counts == {"failed": 1, "expired": 1}
        assert states[orphaned]["state"] == "failed"
        assert states[orphaned]["error_message_safe"] == INTERRUPTED_MESSAGE
        assert _events(conn, orphaned)[-1] == "task_failed"
        assert states[stale_queue]["state"] == "expired"
        assert states[stale_queue]["error_message_safe"] == EXPIRED_MESSAGE
        assert states[live]["state"] == "running"
        assert states[fresh_queue]["state"] == "queued"
        active = conn.execute("SELECT COUNT(*) FROM async_tasks WHERE state IN ('queued', 'running')").fetchone()[0]
        assert active == 2


def test_cancel_after_the_runner_claimed_the_task_requests_cancellation_instead():
    db_path, user_id = _db_with_user()
    with db_conn(db_path) as conn:
        task_id = _new_task(conn, user_id)
        assert mark_task_running(conn, task_id)

        row = request_cancel_task(conn, task_id)

        assert row["state"] == "running"
        assert bool(row["cancel_requested"])


def test_a_task_reaches_exactly_one_terminal_state():
    db_path, user_id = _db_with_user()
    with db_conn(db_path) as conn:
        task_id = _new_task(conn, user_id)
        mark_task_running(conn, task_id)

        mark_task_succeeded(conn, task_id, {"ok": True})
        assert mark_task_cancelled(conn, task_id) is False
        mark_task_succeeded(conn, task_id, {"ok": "again"})

        assert get_async_task(conn, task_id)["state"] == "succeeded"
        assert _events(conn, task_id).count("task_succeeded") == 1
        assert "task_cancelled" not in _events(conn, task_id)


def _run_task(db_path, user_id, handler, correlation_id):
    with db_conn(db_path) as conn:
        task_id = _new_task(conn, user_id, correlation_id)
    runner = LocalTaskRunner(db_path)
    runner.enqueue(task_id, handler)
    runner.shutdown(wait=True)
    with db_conn(db_path) as conn:
        return get_async_task(conn, task_id)


def test_internal_errors_are_not_shown_to_users():
    db_path, user_id = _db_with_user()

    def broken(*_args):
        raise sqlite3.OperationalError("disk I/O error at /srv/private/job_assistant.db")

    row = _run_task(db_path, user_id, broken, "req_internal")

    assert row["state"] == "failed"
    assert row["error_message_safe"] == "Something went wrong (ref req_internal)"


def test_user_facing_errors_keep_their_message():
    db_path, user_id = _db_with_user()

    def not_ready(*_args):
        raise UserFacingError("approved, ready master profile is required")

    row = _run_task(db_path, user_id, not_ready, "req_user")

    assert row["error_message_safe"] == "approved, ready master profile is required"


def _old_queued_task(conn, user_id):
    task_id = _new_task(conn, user_id)
    old = (utc_now() - timedelta(minutes=5)).isoformat()
    conn.execute("UPDATE async_tasks SET created_at_utc = ? WHERE task_id = ?", (old, task_id))
    return task_id


def test_a_queued_task_nobody_is_working_on_is_picked_up_and_runs_once():
    import threading

    db_path, user_id = _db_with_user()
    with db_conn(db_path) as conn:
        orphan = _old_queued_task(conn, user_id)
        fresh = _new_task(conn, user_id)  # too young: its own process may still be about to start it
    calls: list[str] = []
    lock = threading.Lock()

    def handler(task_id, *_args):
        with lock:
            calls.append(task_id)
        return {"ok": True}

    runners = [LocalTaskRunner(db_path, handlers={"manual_search": handler}) for _ in range(2)]
    try:
        started = [runner.requeue_orphans() for runner in runners]
        for runner in runners:
            runner.drain()
    finally:
        for runner in runners:
            runner.shutdown(wait=True)

    assert sum(started) >= 1
    assert calls == [orphan]  # both runners may try, only one wins the claim
    with db_conn(db_path) as conn:
        assert get_async_task(conn, orphan)["state"] == "succeeded"
        assert get_async_task(conn, fresh)["state"] == "queued"


def test_tasks_of_types_without_a_handler_are_left_alone():
    db_path, user_id = _db_with_user()
    with db_conn(db_path) as conn:
        orphan = _old_queued_task(conn, user_id)
    runner = LocalTaskRunner(db_path)  # no handlers registered
    try:
        assert runner.requeue_orphans() == 0
    finally:
        runner.shutdown(wait=True)
    with db_conn(db_path) as conn:
        assert get_async_task(conn, orphan)["state"] == "queued"

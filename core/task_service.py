"""Submitting background tasks: payload validation, capacity limits, persistence, enqueue."""

from __future__ import annotations

import sqlite3
from typing import Any, Protocol

from core.async_tasks import TaskHandler, create_async_task, find_active_duplicate, serialize_async_task
from core.db.connection import begin_write, release_write_lock
from core.errors import ApiError
from core.profile_tasks import run_supplement_profile_task, run_synthesize_profile_task
from core.task_contracts import validate_task_payload
from core.task_handlers import (
    _run_cover_letter_task_handler,
    _run_manual_jd_match_task_handler,
    _run_manual_search_task_handler,
    _run_re_evaluate_task_handler,
    _run_resume_task_handler,
)

TASK_HANDLERS: dict[str, TaskHandler] = {
    "generate_resume": _run_resume_task_handler,
    "generate_cover_letter": _run_cover_letter_task_handler,
    "re_evaluate": _run_re_evaluate_task_handler,
    "manual_search": _run_manual_search_task_handler,
    "manual_jd_match": _run_manual_jd_match_task_handler,
    "synthesize_profile": run_synthesize_profile_task,
    "supplement_profile": run_supplement_profile_task,
}

# One of these per user at a time: a second search with different options would double the job-board requests.
EXCLUSIVE_TASK_TYPES = {"manual_search"}

MAX_ACTIVE_TASKS = 100
MAX_ACTIVE_TASKS_PER_USER = 3


class TaskRunner(Protocol):
    def enqueue(self, task_id: str, handler: TaskHandler) -> None: ...


def submit_task(
    conn: sqlite3.Connection,
    runner: TaskRunner,
    *,
    task_type: str,
    payload: dict[str, Any],
    owner_user_id: int,
    correlation_id: str,
) -> dict[str, Any]:
    """Validate, reserve capacity and create the task in one short transaction, then enqueue it.

    Commits the caller's connection: the runner thread must see the task row.
    """
    handler = TASK_HANDLERS.get(task_type)
    if handler is None:
        raise ApiError(400, 2002, "unsupported task_type")
    try:
        payload = validate_task_payload(task_type, payload)
    except ValueError as exc:
        raise ApiError(400, 2001, str(exc)) from exc

    begin_write(conn)
    duplicate = find_active_duplicate(conn, task_type, owner_user_id, payload)
    if duplicate is not None:
        # The same request is already running (double click, retry): follow that task instead of starting another.
        conn.rollback()
        return serialize_async_task(duplicate)
    if (
        task_type in EXCLUSIVE_TASK_TYPES
        and conn.execute(
            "SELECT 1 FROM async_tasks WHERE owner_user_id = ? AND task_type = ? AND state IN ('queued', 'running')",
            (owner_user_id, task_type),
        ).fetchone()
    ):
        conn.rollback()
        raise ApiError(409, 3004, "a job search is already running")
    active = conn.execute("SELECT COUNT(*) FROM async_tasks WHERE state IN ('queued', 'running')").fetchone()[0]
    owned = conn.execute(
        "SELECT COUNT(*) FROM async_tasks WHERE owner_user_id = ? AND state IN ('queued', 'running')",
        (owner_user_id,),
    ).fetchone()[0]
    if active >= MAX_ACTIVE_TASKS or owned >= MAX_ACTIVE_TASKS_PER_USER:
        conn.rollback()
        raise ApiError(429, 3005, "task queue is full; retry after active tasks complete")
    row = create_async_task(
        conn, task_type=task_type, owner_user_id=owner_user_id, payload=payload, correlation_id=correlation_id
    )
    task = serialize_async_task(row)
    release_write_lock(conn)
    runner.enqueue(task["task_id"], handler)
    return task

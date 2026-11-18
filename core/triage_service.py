"""Swipe decisions on scored jobs: record the action and, for 'accepted', start document generation (ADR-013)."""

from __future__ import annotations

import sqlite3
from typing import Any

from core.async_tasks import deserialize_task_payload, request_cancel_task
from core.errors import ApiError
from core.repositories.decisions import mark_match_viewed, upsert_generation_decision
from core.repositories.triage import clear_triage, set_triage
from core.task_service import TaskRunner, submit_task

TRIAGE_ACTIONS = ("skipped", "waitlisted", "accepted")
_GENERATION_TASKS = ("generate_resume", "generate_cover_letter")


def _require_own_job(conn: sqlite3.Connection, user_id: int, job_id: int) -> None:
    if conn.execute("SELECT 1 FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, user_id)).fetchone() is None:
        raise ApiError(404, 3003, "job not found")


def triage_job(
    conn: sqlite3.Connection,
    runner: TaskRunner,
    *,
    user_id: int,
    job_id: int,
    action: str,
    generate: str | None,
    correlation_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Record the swipe. 'accepted' also records the generation decision and submits the task(s).

    When the per-user task limit is reached the decision stays stored and `queued_for_later` is true; the client
    starts the remaining documents as slots free up (they are listed by `GET /jobs?triage=accepted`).
    """
    _require_own_job(conn, user_id, job_id)
    if action != "accepted":
        set_triage(conn, user_id, job_id, action, None, reason if action == "skipped" else None)
        return {"job_id": job_id, "action": action, "generate": None, "tasks": [], "queued_for_later": False}

    if conn.execute("SELECT 1 FROM evaluations WHERE job_id = ?", (job_id,)).fetchone() is None:
        raise ApiError(409, 3004, "evaluate the job before generating documents")
    generate = generate or "resume"
    both = generate == "resume_and_cover_letter"
    set_triage(conn, user_id, job_id, "accepted", generate)
    mark_match_viewed(conn, job_id, decided_by="swipe")
    upsert_generation_decision(
        conn, job_id=job_id, generate_resume=True, generate_cover_letter=True if both else None, decided_by="swipe"
    )

    requests = [("generate_resume", {"job_id": job_id, "style": "ats"})]
    if both:
        requests.append(("generate_cover_letter", {"job_id": job_id, "tone": "formal"}))
    tasks: list[dict[str, Any]] = []
    queued_for_later = False
    for task_type, payload in requests:
        try:
            tasks.append(
                submit_task(
                    conn,
                    runner,
                    task_type=task_type,
                    payload=payload,
                    owner_user_id=user_id,
                    correlation_id=correlation_id,
                )
            )
        except ApiError as exc:
            if exc.status != 429:
                raise
            queued_for_later = True
            break
    return {
        "job_id": job_id,
        "action": "accepted",
        "generate": generate,
        "tasks": tasks,
        "queued_for_later": queued_for_later,
    }


def undo_triage(conn: sqlite3.Connection, *, user_id: int, job_id: int) -> None:
    """Remove the decision and cancel generation tasks of this job that have not started yet."""
    _require_own_job(conn, user_id, job_id)
    clear_triage(conn, user_id, job_id)
    rows = conn.execute(
        "SELECT * FROM async_tasks WHERE owner_user_id = ? AND state = 'queued' AND task_type IN (?, ?)",
        (user_id, *_GENERATION_TASKS),
    ).fetchall()
    for row in rows:
        if deserialize_task_payload(row).get("job_id") == job_id:
            request_cancel_task(conn, str(row["task_id"]))

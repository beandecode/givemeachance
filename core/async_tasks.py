from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime, timedelta
from functools import partial

from core.db import db_conn
from core.errors import UserFacingError, user_message
from core.logging_setup import log_context
from core.time_utils import utc_now, utc_now_iso

TERMINAL_TASK_STATES = {"succeeded", "failed", "cancelled", "expired"}


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _json_loads_dict(raw: str | None) -> dict:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return {}
    return {}


def _generate_task_id() -> str:
    return f"tsk_{uuid.uuid4().hex[:24]}"


def append_task_event(
    conn: sqlite3.Connection,
    task_id: str,
    event_type: str,
    stage_name: str,
    progress_percent: int,
    message: str,
    correlation_id: str,
    delta_text: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO task_events (
            task_id, event_type, stage_name, progress_percent, message,
            delta_text, correlation_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            str(event_type),
            str(stage_name),
            int(max(0, min(progress_percent, 100))),
            str(message),
            delta_text,
            str(correlation_id),
            utc_now_iso(),
        ),
    )


def create_async_task(
    conn: sqlite3.Connection,
    task_type: str,
    owner_user_id: int,
    payload: dict,
    correlation_id: str,
) -> sqlite3.Row:
    now = utc_now_iso()
    task_id = _generate_task_id()
    conn.execute(
        """
        INSERT INTO async_tasks (
            task_id, task_type, owner_user_id, state,
            payload_json, result_json, result_ref,
            error_code, error_message_safe,
            progress_percent, progress_stage,
            cancel_requested,
            correlation_id,
            created_at_utc, started_at_utc, finished_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
        """,
        (
            task_id,
            str(task_type),
            int(owner_user_id),
            "queued",
            _json_dumps(payload),
            None,
            None,
            None,
            None,
            0,
            "queued",
            0,
            str(correlation_id),
            now,
        ),
    )
    append_task_event(
        conn,
        task_id=task_id,
        event_type="task_queued",
        stage_name="queued",
        progress_percent=0,
        message="task queued",
        correlation_id=correlation_id,
    )
    row = get_async_task(conn, task_id)
    if row is None:
        raise RuntimeError("failed to create async task")
    return row


def find_active_duplicate(
    conn: sqlite3.Connection, task_type: str, owner_user_id: int, payload: dict
) -> sqlite3.Row | None:
    """A queued or running task of the same owner and type with exactly this payload (a double click, a retry)."""
    row = conn.execute(
        """
        SELECT task_id FROM async_tasks
        WHERE owner_user_id = ? AND task_type = ? AND payload_json = ? AND state IN ('queued', 'running')
        ORDER BY id DESC LIMIT 1
        """,
        (int(owner_user_id), str(task_type), _json_dumps(payload)),
    ).fetchone()
    return get_async_task(conn, str(row["task_id"])) if row is not None else None


def get_async_task(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, task_id, task_type, owner_user_id, state,
               payload_json, result_json, result_ref,
               error_code, error_message_safe,
               progress_percent, progress_stage,
               cancel_requested,
               correlation_id,
               created_at_utc, started_at_utc, finished_at_utc
        FROM async_tasks
        WHERE task_id = ?
        """,
        (str(task_id),),
    ).fetchone()


def _task_job_id(row: sqlite3.Row) -> int | None:
    """The job a task works on (document generation), so clients can show progress on that job."""
    if "payload_json" not in row.keys():
        return None
    job_id = _json_loads_dict(row["payload_json"]).get("job_id")
    return job_id if isinstance(job_id, int) and not isinstance(job_id, bool) else None


def serialize_async_task(row: sqlite3.Row) -> dict:
    return {
        "task_id": str(row["task_id"]),
        "task_type": str(row["task_type"]),
        "owner_user_id": int(row["owner_user_id"]),
        "state": str(row["state"]),
        "correlation_id": str(row["correlation_id"]),
        "created_at_utc": row["created_at_utc"],
        "started_at_utc": row["started_at_utc"],
        "finished_at_utc": row["finished_at_utc"],
        "progress_percent": int(row["progress_percent"] or 0),
        "progress_stage": str(row["progress_stage"] or ""),
        "error_code": int(row["error_code"]) if row["error_code"] is not None else None,
        "error_message_safe": str(row["error_message_safe"]) if row["error_message_safe"] is not None else None,
        "result_ref": str(row["result_ref"]) if row["result_ref"] is not None else None,
        "cancel_requested": bool(row["cancel_requested"]),
        "job_id": _task_job_id(row),
    }


def deserialize_task_payload(row: sqlite3.Row) -> dict:
    return _json_loads_dict(row["payload_json"])


def deserialize_task_result(row: sqlite3.Row) -> dict:
    return _json_loads_dict(row["result_json"])


def _transition(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    to_state: str,
    from_states: tuple[str, ...],
    assignments: str = "",
    params: tuple = (),
) -> sqlite3.Row | None:
    """Move a task to `to_state` only if it is currently in one of `from_states`.

    The state check and the update are one statement, so concurrent transitions (for example a
    cancel racing a completion) cannot both win. Returns the updated row, or None if no change.
    """
    placeholders = ", ".join("?" for _ in from_states)
    extra = f", {assignments}" if assignments else ""
    cursor = conn.execute(
        f"UPDATE async_tasks SET state = ?{extra} WHERE task_id = ? AND state IN ({placeholders})",
        (to_state, *params, str(task_id), *from_states),
    )
    if cursor.rowcount != 1:
        return None
    return get_async_task(conn, task_id)


def mark_task_running(conn: sqlite3.Connection, task_id: str) -> bool:
    now = utc_now_iso()
    row = _transition(
        conn,
        task_id,
        to_state="running",
        from_states=("queued",),
        assignments=(
            "started_at_utc = COALESCE(started_at_utc, ?), heartbeat_at_utc = ?, progress_percent = 5, "
            "progress_stage = 'running', error_code = NULL, error_message_safe = NULL"
        ),
        params=(now, now),
    )
    if row is None:
        return False
    append_task_event(
        conn,
        task_id=task_id,
        event_type="task_running",
        stage_name="running",
        progress_percent=5,
        message="task running",
        correlation_id=str(row["correlation_id"]),
    )
    return True


def mark_task_progress(
    conn: sqlite3.Connection,
    task_id: str,
    stage_name: str,
    progress_percent: int,
    message: str,
    delta_text: str | None = None,
) -> None:
    percent = int(max(0, min(progress_percent, 100)))
    cursor = conn.execute(
        """
        UPDATE async_tasks
        SET progress_percent = ?, progress_stage = ?, heartbeat_at_utc = ?
        WHERE task_id = ? AND state = 'running'
        """,
        (percent, str(stage_name), utc_now_iso(), str(task_id)),
    )
    if cursor.rowcount != 1:
        return
    row = get_async_task(conn, task_id)
    assert row is not None
    append_task_event(
        conn,
        task_id=task_id,
        event_type="task_progress",
        stage_name=str(stage_name),
        progress_percent=percent,
        message=str(message),
        correlation_id=str(row["correlation_id"]),
        delta_text=delta_text,
    )


def mark_task_succeeded(conn: sqlite3.Connection, task_id: str, result: dict, result_ref: str | None = None) -> None:
    row = _transition(
        conn,
        task_id,
        to_state="succeeded",
        from_states=("queued", "running"),
        assignments=(
            "result_json = ?, result_ref = ?, error_code = NULL, error_message_safe = NULL, "
            "progress_percent = 100, progress_stage = 'succeeded', finished_at_utc = ?"
        ),
        params=(_json_dumps(result), result_ref, utc_now_iso()),
    )
    if row is None:
        return
    append_task_event(
        conn,
        task_id=task_id,
        event_type="task_succeeded",
        stage_name="succeeded",
        progress_percent=100,
        message="task succeeded",
        correlation_id=str(row["correlation_id"]),
    )


def mark_task_failed(
    conn: sqlite3.Connection,
    task_id: str,
    error_message_safe: str,
    error_code: int = 5002,
    *,
    to_state: str = "failed",
) -> None:
    safe_message = str(error_message_safe or "task execution failed").strip() or "task execution failed"
    row = _transition(
        conn,
        task_id,
        to_state=to_state,
        from_states=("queued", "running"),
        assignments="error_code = ?, error_message_safe = ?, progress_stage = ?, finished_at_utc = ?",
        params=(int(error_code), safe_message[:300], to_state, utc_now_iso()),
    )
    if row is None:
        return
    append_task_event(
        conn,
        task_id=task_id,
        event_type=f"task_{to_state}",
        stage_name=to_state,
        progress_percent=int(row["progress_percent"] or 0),
        message=safe_message[:160],
        correlation_id=str(row["correlation_id"]),
    )


def mark_task_cancelled(
    conn: sqlite3.Connection,
    task_id: str,
    message: str = "task cancelled",
    from_states: tuple[str, ...] = ("queued", "running"),
) -> bool:
    row = _transition(
        conn,
        task_id,
        to_state="cancelled",
        from_states=from_states,
        assignments=("progress_stage = 'cancelled', finished_at_utc = ?, error_code = NULL, error_message_safe = NULL"),
        params=(utc_now_iso(),),
    )
    if row is None:
        return False
    append_task_event(
        conn,
        task_id=task_id,
        event_type="task_cancelled",
        stage_name="cancelled",
        progress_percent=int(row["progress_percent"] or 0),
        message=str(message)[:160],
        correlation_id=str(row["correlation_id"]),
    )
    return True


def request_cancel_task(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
    """Cancel a queued task now; ask a running one to stop at its next stage boundary."""
    row = get_async_task(conn, task_id)
    if row is None or str(row["state"]) in TERMINAL_TASK_STATES:
        return row

    # Only cancels if the runner has not claimed it meanwhile; otherwise fall through.
    if mark_task_cancelled(conn, task_id, message="task cancelled before execution", from_states=("queued",)):
        return get_async_task(conn, task_id)

    cursor = conn.execute(
        "UPDATE async_tasks SET cancel_requested = 1 WHERE task_id = ? AND state = 'running' AND cancel_requested = 0",
        (str(task_id),),
    )
    row = get_async_task(conn, task_id)
    if cursor.rowcount == 1 and row is not None:
        append_task_event(
            conn,
            task_id=task_id,
            event_type="task_cancel_requested",
            stage_name=str(row["state"]),
            progress_percent=int(row["progress_percent"] or 0),
            message="cancellation requested",
            correlation_id=str(row["correlation_id"]),
        )
    return row


INTERRUPTED_MESSAGE = "The task was interrupted (server restart or crash). Please try again."
EXPIRED_MESSAGE = "The task expired before it could start. Please try again."


def recover_stale_tasks(
    conn: sqlite3.Connection,
    *,
    stale_running_after: timedelta,
    expire_queued_after: timedelta,
    now: datetime | None = None,
) -> dict[str, int]:
    """Finish tasks whose worker is gone so they stop counting toward capacity.

    A running task whose heartbeat is older than `stale_running_after` becomes `failed`; a queued
    task never claimed within `expire_queued_after` becomes `expired`. Live runners refresh
    heartbeats far more often than the threshold, so tasks of other processes are left alone.
    """
    current = now or utc_now()
    counts = {"failed": 0, "expired": 0}
    rows = conn.execute(
        """
        SELECT task_id, state, created_at_utc, started_at_utc, heartbeat_at_utc
        FROM async_tasks
        WHERE state IN ('queued', 'running')
        """
    ).fetchall()
    for row in rows:
        if row["state"] == "running":
            last_seen = _parse_utc(row["heartbeat_at_utc"] or row["started_at_utc"] or row["created_at_utc"])
            if last_seen is None or current - last_seen > stale_running_after:
                mark_task_failed(conn, row["task_id"], INTERRUPTED_MESSAGE, error_code=5002)
                counts["failed"] += 1
        else:
            created = _parse_utc(row["created_at_utc"])
            if created is None or current - created > expire_queued_after:
                mark_task_failed(conn, row["task_id"], EXPIRED_MESSAGE, error_code=5002, to_state="expired")
                counts["expired"] += 1
    return counts


def _parse_utc(value: str | None) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class TaskCancelled(Exception):
    """Cooperative cancellation before the next side-effecting stage."""


TaskHandler = Callable[[str, dict, int, str, Callable[[str, int, str], None]], dict]


class LocalTaskRunner:
    """In-process task executor with heartbeats and periodic recovery of orphaned tasks."""

    heartbeat_interval = timedelta(seconds=30)
    stale_running_after = timedelta(minutes=5)
    expire_queued_after = timedelta(minutes=30)
    # A queued task nobody has started after this long is picked up by any live runner (its own process may
    # have restarted, or every worker thread may be busy). `mark_task_running` lets exactly one runner win.
    requeue_after = timedelta(seconds=60)

    def __init__(self, db_path: str, max_workers: int = 2, handlers: Mapping[str, TaskHandler] | None = None):
        self._db_path = str(db_path)
        self._handlers = dict(handlers or {})
        self._pending_ids: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="gmc-task")
        self._active: set[str] = set()
        self._futures: set[Future] = set()
        self._active_lock = threading.Lock()
        self._stopping = threading.Event()
        self.recover()
        self._maintenance = threading.Thread(target=self._maintain, name="gmc-task-heartbeat", daemon=True)
        self._maintenance.start()

    def enqueue(self, task_id: str, handler: TaskHandler) -> None:
        future = self._executor.submit(self._run, str(task_id), handler)
        with self._active_lock:
            self._futures.add(future)
            self._pending_ids.add(str(task_id))
        future.add_done_callback(partial(self._forget, task_id=str(task_id)))

    def _forget(self, future: Future, task_id: str | None = None) -> None:
        with self._active_lock:
            self._futures.discard(future)
            if task_id is not None:
                self._pending_ids.discard(task_id)

    def requeue_orphans(self, min_age: timedelta | None = None) -> int:
        """Start queued tasks that nobody is working on; returns how many were handed to this runner."""
        cutoff = (utc_now() - (self.requeue_after if min_age is None else min_age)).isoformat()
        with db_conn(self._db_path) as conn:
            rows = conn.execute(
                "SELECT task_id, task_type FROM async_tasks WHERE state = 'queued' AND created_at_utc <= ?", (cutoff,)
            ).fetchall()
        started = 0
        for row in rows:
            task_id, handler = str(row["task_id"]), self._handlers.get(str(row["task_type"]))
            with self._active_lock:
                mine = task_id in self._pending_ids
            if handler is not None and not mine:
                self.enqueue(task_id, handler)
                started += 1
        return started

    def drain(self, timeout: float | None = None) -> None:
        """Wait until every task enqueued so far has finished (the runner stays usable)."""
        with self._active_lock:
            pending = list(self._futures)
        wait(pending, timeout=timeout)

    def shutdown(self, wait: bool = True) -> None:
        self._stopping.set()
        self._executor.shutdown(wait=wait)
        if wait:
            self._maintenance.join()

    def recover(self) -> dict[str, int]:
        with db_conn(self._db_path) as conn:
            counts = recover_stale_tasks(
                conn, stale_running_after=self.stale_running_after, expire_queued_after=self.expire_queued_after
            )
        if counts["failed"] or counts["expired"]:
            logging.getLogger(__name__).warning("Recovered stale tasks: %s", counts)
        return counts

    def _beat(self) -> None:
        with self._active_lock:
            active = sorted(self._active)
        if not active:
            return
        placeholders = ", ".join("?" for _ in active)
        with db_conn(self._db_path) as conn:
            conn.execute(
                f"UPDATE async_tasks SET heartbeat_at_utc = ? WHERE state = 'running' AND task_id IN ({placeholders})",
                (utc_now_iso(), *active),
            )

    def _maintain(self) -> None:
        while not self._stopping.wait(self.heartbeat_interval.total_seconds()):
            try:
                self._beat()
                self.recover()
                self.requeue_orphans()
            except Exception:
                logging.getLogger(__name__).exception("Task heartbeat/recovery failed")

    def _run(self, task_id: str, handler: TaskHandler) -> None:
        with db_conn(self._db_path) as conn:
            row = get_async_task(conn, task_id)
            if row is None:
                return
            if str(row["state"]) != "queued":
                return
            if not mark_task_running(conn, task_id):
                return
            row = get_async_task(conn, task_id)
            if row is None:
                return
            payload = deserialize_task_payload(row)
            owner_user_id = int(row["owner_user_id"])
            correlation_id = str(row["correlation_id"])
        with self._active_lock:
            self._active.add(task_id)
        try:
            with log_context(correlation_id=correlation_id, task_id=task_id):
                self._execute(task_id, handler, payload, owner_user_id, correlation_id)
        finally:
            with self._active_lock:
                self._active.discard(task_id)

    def _execute(self, task_id: str, handler: TaskHandler, payload: dict, owner_user_id: int, correlation_id: str):

        def report_progress(stage_name: str, percent: int, message: str) -> None:
            with db_conn(self._db_path) as progress_conn:
                latest = get_async_task(progress_conn, task_id)
                # "persisted" reports an already committed result; preserve it.
                if latest is not None and bool(latest["cancel_requested"]) and stage_name != "persisted":
                    raise TaskCancelled()
                mark_task_progress(
                    progress_conn,
                    task_id=task_id,
                    stage_name=stage_name,
                    progress_percent=percent,
                    message=message,
                )

        try:
            result = handler(task_id, payload, owner_user_id, correlation_id, report_progress)
            with db_conn(self._db_path) as conn:
                latest = get_async_task(conn, task_id)
                if latest is None:
                    return
                result_ref = None
                if isinstance(result, dict):
                    result_ref = str(result.get("result_ref")) if result.get("result_ref") is not None else None
                mark_task_succeeded(
                    conn,
                    task_id,
                    result=result if isinstance(result, dict) else {"result": result},
                    result_ref=result_ref,
                )
        except TaskCancelled:
            with db_conn(self._db_path) as conn:
                mark_task_cancelled(conn, task_id, message="task cancelled at stage boundary")
        except Exception as exc:
            if not isinstance(exc, UserFacingError):
                logging.getLogger(__name__).exception("Task %s failed (correlation_id=%s)", task_id, correlation_id)
            with db_conn(self._db_path) as conn:
                mark_task_failed(conn, task_id, error_message_safe=user_message(exc, correlation_id), error_code=5002)

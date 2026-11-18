"""Swipe decisions (skipped / waitlisted / accepted) per user and job."""

from __future__ import annotations

import sqlite3

from core.time_utils import utc_now_iso


def set_triage(
    conn: sqlite3.Connection,
    user_id: int,
    job_id: int,
    action: str,
    generate: str | None,
    reason: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO job_triage (user_id, job_id, action, generate, reason, decided_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, job_id) DO UPDATE SET
            action=excluded.action, generate=excluded.generate, reason=excluded.reason,
            decided_at=excluded.decided_at
        """,
        (user_id, job_id, action, generate, reason, utc_now_iso()),
    )


def clear_triage(conn: sqlite3.Connection, user_id: int, job_id: int) -> bool:
    cursor = conn.execute("DELETE FROM job_triage WHERE user_id = ? AND job_id = ?", (user_id, job_id))
    return cursor.rowcount == 1

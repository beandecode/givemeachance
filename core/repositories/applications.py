"""Application tracking status per job."""

from __future__ import annotations

import sqlite3

from core.time_utils import utc_now_iso


def upsert_application_status(conn: sqlite3.Connection, job_id: int, status: str, status_note: str = "") -> None:
    conn.execute(
        """
        INSERT INTO applications (job_id, status, status_note, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            status=excluded.status,
            status_note=excluded.status_note,
            updated_at=excluded.updated_at
        """,
        (job_id, status, status_note, utc_now_iso()),
    )


def mark_application_materials_ready(conn: sqlite3.Connection, job_id: int, note: str) -> None:
    """Generating another document must not undo a user's application progress."""
    conn.execute(
        """INSERT INTO applications (job_id, status, status_note, updated_at)
           VALUES (?, 'ready', ?, ?)
           ON CONFLICT(job_id) DO UPDATE SET
               status = 'ready', updated_at = excluded.updated_at
           WHERE applications.status IN ('draft', 'ready')""",
        (job_id, note, utc_now_iso()),
    )


def set_follow_up(conn: sqlite3.Connection, job_id: int, follow_up_at: str | None) -> None:
    """Set or clear the follow-up date (YYYY-MM-DD); creates the application row when there is none."""
    conn.execute(
        """
        INSERT INTO applications (job_id, status, status_note, updated_at, follow_up_at)
        VALUES (?, 'draft', '', ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET follow_up_at=excluded.follow_up_at, updated_at=excluded.updated_at
        """,
        (job_id, utc_now_iso(), follow_up_at),
    )

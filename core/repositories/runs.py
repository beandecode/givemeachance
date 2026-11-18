"""Pipeline run log and failed-job records."""

from __future__ import annotations

import sqlite3

from core.time_utils import utc_now_iso


def log_run(conn: sqlite3.Connection, run_key: str, stage: str, status: str, message: str = "") -> None:
    """Track pipeline stages for operations and troubleshooting."""
    conn.execute(
        "INSERT INTO pipeline_runs (run_key, stage, status, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (run_key, stage, status, message, utc_now_iso()),
    )


def log_failed_job(
    conn: sqlite3.Connection, run_key: str, stage: str, error_message: str, job_id: int | None = None
) -> None:
    conn.execute(
        """
        INSERT INTO failed_jobs (run_key, job_id, stage, error_message, retry_count, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (run_key, job_id, stage, error_message[:2000], utc_now_iso()),
    )

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from core.db.connection import connect
from core.time_utils import utc_now_iso, utc_today_iso


@contextmanager
def _own_write_transaction(db_path: str) -> Iterator[sqlite3.Connection]:
    """A dedicated connection holding the writer lock only for the quota update itself."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_api_usage_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_usage_daily (
            provider TEXT NOT NULL,
            usage_date TEXT NOT NULL,
            used_count INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(provider, usage_date)
        )
        """
    )


def _ensure_api_usage_subject_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_usage_daily_subject (
            provider TEXT NOT NULL,
            usage_date TEXT NOT NULL,
            subject TEXT NOT NULL,
            used_count INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(provider, usage_date, subject)
        )
        """
    )


def get_daily_api_usage_for_subject(db_path: str, subject: str, limits: dict[str, int]) -> list[dict[str, Any]]:
    """Return daily usage summary for each provider limit for one subject."""
    usage_db_path = Path(db_path)
    usage_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(usage_db_path) as conn:
        return get_daily_api_usage_for_subject_with_conn(conn, subject, limits)


def get_daily_api_usage_for_subject_with_conn(
    conn: sqlite3.Connection, subject: str, limits: dict[str, int]
) -> list[dict[str, Any]]:
    """Return subject usage summary using an existing connection."""
    _ensure_api_usage_subject_table(conn)
    usage_date = utc_today_iso()
    rows = conn.execute(
        "SELECT provider, used_count FROM api_usage_daily_subject WHERE usage_date = ? AND subject = ?",
        (usage_date, subject),
    ).fetchall()

    usage_by_provider = {str(row[0]): int(row[1]) for row in rows}
    summary: list[dict[str, Any]] = []

    for provider, configured_limit in limits.items():
        daily_limit = max(0, int(configured_limit))
        used = max(0, int(usage_by_provider.get(provider, 0)))
        remaining = max(0, daily_limit - used)
        percent_used = 0
        if daily_limit > 0:
            percent_used = min(100, int((used * 100) / daily_limit))

        summary.append(
            {
                "provider": provider,
                "usage_date": usage_date,
                "limit": daily_limit,
                "used": used,
                "remaining": remaining,
                "percent_used": percent_used,
                "subject": subject,
            }
        )

    return summary


def consume_api_quota(
    db_path: str,
    provider: str,
    daily_limit: int,
    units: int = 1,
) -> tuple[bool, int]:
    """Atomically consume provider quota for current UTC day.

    Always commits on its own connection, so recorded usage survives a rollback of the
    caller's work (the provider call happened either way).
    Returns (allowed, used_count_after_or_current).
    """
    if daily_limit < 0:
        raise ValueError("daily_limit must be >= 0")
    if units <= 0:
        raise ValueError("units must be > 0")

    usage_date = utc_today_iso()
    now = utc_now_iso()
    with _own_write_transaction(db_path) as conn:
        _ensure_api_usage_table(conn)
        row = conn.execute(
            "SELECT used_count FROM api_usage_daily WHERE provider = ? AND usage_date = ?",
            (provider, usage_date),
        ).fetchone()
        current_used = int(row[0]) if row is not None else 0
        if current_used + units > daily_limit:
            return False, current_used

        next_used = current_used + units
        conn.execute(
            """
            INSERT INTO api_usage_daily (provider, usage_date, used_count, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(provider, usage_date) DO UPDATE SET
                used_count = excluded.used_count,
                updated_at = excluded.updated_at
            """,
            (provider, usage_date, next_used, now),
        )
    return True, next_used


def consume_dual_api_quota(
    db_path: str,
    provider: str,
    subject: str,
    subject_daily_limit: int,
    global_daily_limit: int,
    units: int = 1,
) -> tuple[bool, dict[str, Any]]:
    """Consume both subject-level and global-level quota atomically for current UTC day.

    Always commits on its own connection (see `consume_api_quota`).
    """
    if subject_daily_limit < 0 or global_daily_limit < 0:
        raise ValueError("limits must be >= 0")
    if units <= 0:
        raise ValueError("units must be > 0")

    usage_date = utc_today_iso()
    now = utc_now_iso()
    normalized_subject = str(subject or "anonymous").strip() or "anonymous"

    def _consume_with_connection(active_conn: sqlite3.Connection) -> tuple[bool, dict[str, Any]]:
        _ensure_api_usage_table(active_conn)
        _ensure_api_usage_subject_table(active_conn)

        global_row = active_conn.execute(
            "SELECT used_count FROM api_usage_daily WHERE provider = ? AND usage_date = ?",
            (provider, usage_date),
        ).fetchone()
        subject_row = active_conn.execute(
            """
            SELECT used_count
            FROM api_usage_daily_subject
            WHERE provider = ? AND usage_date = ? AND subject = ?
            """,
            (provider, usage_date, normalized_subject),
        ).fetchone()

        current_global_used = int(global_row[0]) if global_row is not None else 0
        current_subject_used = int(subject_row[0]) if subject_row is not None else 0

        if current_subject_used + units > subject_daily_limit:
            return (
                False,
                {
                    "reason": "subject_quota_reached",
                    "provider": provider,
                    "subject": normalized_subject,
                    "subject_used": current_subject_used,
                    "subject_limit": int(subject_daily_limit),
                    "global_used": current_global_used,
                    "global_limit": int(global_daily_limit),
                },
            )

        if current_global_used + units > global_daily_limit:
            return (
                False,
                {
                    "reason": "global_quota_reached",
                    "provider": provider,
                    "subject": normalized_subject,
                    "subject_used": current_subject_used,
                    "subject_limit": int(subject_daily_limit),
                    "global_used": current_global_used,
                    "global_limit": int(global_daily_limit),
                },
            )

        next_subject_used = current_subject_used + units
        next_global_used = current_global_used + units

        active_conn.execute(
            """
            INSERT INTO api_usage_daily_subject (provider, usage_date, subject, used_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider, usage_date, subject) DO UPDATE SET
                used_count = excluded.used_count,
                updated_at = excluded.updated_at
            """,
            (provider, usage_date, normalized_subject, next_subject_used, now),
        )
        active_conn.execute(
            """
            INSERT INTO api_usage_daily (provider, usage_date, used_count, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(provider, usage_date) DO UPDATE SET
                used_count = excluded.used_count,
                updated_at = excluded.updated_at
            """,
            (provider, usage_date, next_global_used, now),
        )

        return (
            True,
            {
                "reason": "ok",
                "provider": provider,
                "subject": normalized_subject,
                "subject_used": next_subject_used,
                "subject_limit": int(subject_daily_limit),
                "global_used": next_global_used,
                "global_limit": int(global_daily_limit),
            },
        )

    with _own_write_transaction(db_path) as conn:
        return _consume_with_connection(conn)

"""Viewed-match acknowledgements and document generation decisions."""

from __future__ import annotations

import sqlite3

from core.time_utils import utc_now_iso


def mark_match_viewed(conn: sqlite3.Connection, job_id: int, decided_by: str = "user") -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO generation_decisions (
            job_id, viewed_match_at, decision_generate_resume,
            decision_generate_cover_letter, decided_by, created_at, updated_at
        ) VALUES (?, ?, 0, 0, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            viewed_match_at=excluded.viewed_match_at,
            decided_by=excluded.decided_by,
            updated_at=excluded.updated_at
        """,
        (job_id, now, decided_by, now, now),
    )


def upsert_generation_decision(
    conn: sqlite3.Connection,
    job_id: int,
    generate_resume: bool | None,
    generate_cover_letter: bool | None,
    decided_by: str = "user",
) -> sqlite3.Row:
    now = utc_now_iso()
    current = conn.execute(
        """
        SELECT decision_generate_resume, decision_generate_cover_letter
        FROM generation_decisions
        WHERE job_id = ?
        """,
        (job_id,),
    ).fetchone()

    current_resume = int(current["decision_generate_resume"]) if current is not None else 0
    current_cover_letter = int(current["decision_generate_cover_letter"]) if current is not None else 0

    next_resume = current_resume if generate_resume is None else int(bool(generate_resume))
    next_cover_letter = current_cover_letter if generate_cover_letter is None else int(bool(generate_cover_letter))

    conn.execute(
        """
        INSERT INTO generation_decisions (
            job_id, viewed_match_at, decision_generate_resume,
            decision_generate_cover_letter, decided_by, created_at, updated_at
        ) VALUES (?, NULL, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            decision_generate_resume=excluded.decision_generate_resume,
            decision_generate_cover_letter=excluded.decision_generate_cover_letter,
            decided_by=excluded.decided_by,
            updated_at=excluded.updated_at
        """,
        (job_id, next_resume, next_cover_letter, decided_by, now, now),
    )

    row = conn.execute(
        """
        SELECT id, job_id, viewed_match_at, decision_generate_resume,
               decision_generate_cover_letter, decided_by, created_at, updated_at
        FROM generation_decisions
        WHERE job_id = ?
        """,
        (job_id,),
    ).fetchone()
    return row


def get_generation_decision(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, job_id, viewed_match_at, decision_generate_resume,
               decision_generate_cover_letter, decided_by, created_at, updated_at
        FROM generation_decisions
        WHERE job_id = ?
        """,
        (job_id,),
    ).fetchone()

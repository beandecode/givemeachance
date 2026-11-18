"""Versioned Master Profiles and their review status."""

from __future__ import annotations

import sqlite3

from core.time_utils import utc_now_iso


def insert_candidate_profile(
    conn: sqlite3.Connection,
    source_bundle_json: str,
    master_profile_json: str,
    model_name: str,
    user_id: int | None = None,
) -> sqlite3.Row:
    now = utc_now_iso()
    if user_id is None:
        next_version = (
            int(conn.execute("SELECT COALESCE(MAX(profile_version), 0) AS v FROM candidate_profiles").fetchone()["v"])
            + 1
        )
    else:
        next_version = (
            int(
                conn.execute(
                    "SELECT COALESCE(MAX(profile_version), 0) AS v FROM candidate_profiles WHERE user_id = ?",
                    (int(user_id),),
                ).fetchone()["v"]
            )
            + 1
        )

    cursor = conn.execute(
        """
        INSERT INTO candidate_profiles (
            profile_version, user_id, source_bundle_json, master_profile_json, model_name, created_at,
            review_status, review_note, reviewed_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', '', NULL)
        """,
        (next_version, user_id, source_bundle_json, master_profile_json, model_name, now),
    )
    assert cursor.lastrowid is not None  # set by a successful INSERT
    profile_id = int(cursor.lastrowid)

    row = conn.execute(
        """
        SELECT id, profile_version, user_id, source_bundle_json, master_profile_json, model_name, created_at,
               review_status, review_note, reviewed_at_utc
        FROM candidate_profiles
        WHERE id = ?
        """,
        (profile_id,),
    ).fetchone()
    return row


def get_candidate_profile(conn: sqlite3.Connection, profile_id: int, user_id: int | None = None) -> sqlite3.Row | None:
    if user_id is None:
        return conn.execute(
            """
            SELECT id, profile_version, user_id, source_bundle_json, master_profile_json, model_name, created_at,
                   review_status, review_note, reviewed_at_utc
            FROM candidate_profiles
            WHERE id = ?
            """,
            (profile_id,),
        ).fetchone()

    return conn.execute(
        """
        SELECT id, profile_version, user_id, source_bundle_json, master_profile_json, model_name, created_at,
               review_status, review_note, reviewed_at_utc
        FROM candidate_profiles
        WHERE id = ? AND user_id = ?
        """,
        (profile_id, int(user_id)),
    ).fetchone()


def get_latest_candidate_profile(conn: sqlite3.Connection, user_id: int | None = None) -> sqlite3.Row | None:
    if user_id is None:
        return conn.execute(
            """
            SELECT id, profile_version, user_id, source_bundle_json, master_profile_json, model_name, created_at,
                   review_status, review_note, reviewed_at_utc
            FROM candidate_profiles
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    return conn.execute(
        """
        SELECT id, profile_version, user_id, source_bundle_json, master_profile_json, model_name, created_at,
               review_status, review_note, reviewed_at_utc
        FROM candidate_profiles
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(user_id),),
    ).fetchone()


def update_candidate_profile_review(
    conn: sqlite3.Connection,
    *,
    profile_id: int,
    user_id: int | None,
    review_status: str,
    review_note: str = "",
) -> sqlite3.Row | None:
    status = str(review_status or "").strip().lower()
    if status not in {"approved", "needs_changes"}:
        raise ValueError("invalid review_status")

    target = get_candidate_profile(conn, profile_id, user_id=user_id)
    if target is None:
        return None

    reviewed_at = utc_now_iso()
    conn.execute(
        """
        UPDATE candidate_profiles
        SET review_status = ?, review_note = ?, reviewed_at_utc = ?
        WHERE id = ?
        """,
        (status, str(review_note or "").strip(), reviewed_at, int(profile_id)),
    )
    return get_candidate_profile(conn, profile_id, user_id=user_id)


def list_profile_versions(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    """Version metadata (no profile JSON), newest first."""
    return conn.execute(
        """
        SELECT id, profile_version, model_name, created_at, review_status, review_note, reviewed_at_utc
        FROM candidate_profiles
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (int(user_id),),
    ).fetchall()

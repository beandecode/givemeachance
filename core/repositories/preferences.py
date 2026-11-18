"""Per-user preference sections stored as JSON rows (the typed model lives in core/preferences_service.py)."""

from __future__ import annotations

import sqlite3

from core.time_utils import utc_now_iso


def read_sections(conn: sqlite3.Connection, user_id: int) -> dict[str, str]:
    rows = conn.execute("SELECT key, value_json FROM user_preferences WHERE user_id = ?", (user_id,)).fetchall()
    return {str(row["key"]): str(row["value_json"]) for row in rows}


def write_sections(conn: sqlite3.Connection, user_id: int, sections: dict[str, str]) -> None:
    now = utc_now_iso()
    for key, value_json in sections.items():
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, key, value_json, updated_at_utc)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET
                value_json=excluded.value_json, updated_at_utc=excluded.updated_at_utc
            """,
            (user_id, key, value_json, now),
        )

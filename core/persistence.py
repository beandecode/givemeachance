from __future__ import annotations

import sqlite3

from core.user_scope import is_admin_user


def job_visibility_clause(user_row, alias: str = "j") -> tuple[str, tuple]:
    if user_row is None:
        return f"{alias}.id = -1", ()
    if is_admin_user(user_row):
        return "1=1", ()
    return f"{alias}.owner_user_id = ?", (int(user_row["id"]),)


def load_scoped_job(conn: sqlite3.Connection, job_id: int, user_row):
    if user_row is None:
        return None
    if is_admin_user(user_row):
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return conn.execute(
        "SELECT * FROM jobs WHERE id = ? AND owner_user_id = ?",
        (job_id, int(user_row["id"])),
    ).fetchone()

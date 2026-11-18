"""Versioned documents (resumes and cover letters). Each save is a new version; nothing is overwritten."""

from __future__ import annotations

import sqlite3
from typing import Literal

from core.time_utils import utc_now_iso

DocumentKind = Literal["resume", "cover_letter"]
DOCUMENT_TABLES: dict[str, str] = {"resume": "generated_resumes", "cover_letter": "cover_letters"}
_COLUMNS = "id, job_id, version, content_md, source_profile_id, evidence_map_json, created_at, origin"


def _table(kind: str) -> str:
    try:
        return DOCUMENT_TABLES[kind]
    except KeyError:
        raise ValueError(f"unknown document kind: {kind}") from None


def insert_document_version(
    conn: sqlite3.Connection,
    kind: str,
    *,
    job_id: int,
    content_md: str,
    source_profile_id: int | None,
    evidence_map_json: str,
    origin: str = "generated",
) -> sqlite3.Row:
    """Append the next version. Call inside a write transaction so the version number can't race."""
    table = _table(kind)
    next_version = (
        int(conn.execute(f"SELECT COALESCE(MAX(version), 0) FROM {table} WHERE job_id = ?", (job_id,)).fetchone()[0])
        + 1
    )
    cursor = conn.execute(
        f"""INSERT INTO {table} (job_id, version, content_md, source_profile_id, evidence_map_json, created_at, origin)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (job_id, next_version, content_md, source_profile_id, evidence_map_json, utc_now_iso(), origin),
    )
    assert cursor.lastrowid is not None  # set by a successful INSERT
    row = conn.execute(f"SELECT {_COLUMNS} FROM {table} WHERE id = ?", (cursor.lastrowid,)).fetchone()
    assert row is not None
    return row


def insert_generated_resume(
    conn: sqlite3.Connection,
    job_id: int,
    content_md: str,
    source_profile_id: int | None,
    evidence_map_json: str,
) -> sqlite3.Row:
    return insert_document_version(
        conn,
        "resume",
        job_id=job_id,
        content_md=content_md,
        source_profile_id=source_profile_id,
        evidence_map_json=evidence_map_json,
    )


def get_owned_document(conn: sqlite3.Connection, kind: str, document_id: int, user_id: int) -> sqlite3.Row | None:
    table = _table(kind)
    return conn.execute(
        f"""SELECT {", ".join("d." + column.strip() for column in _COLUMNS.split(","))}
            FROM {table} d JOIN jobs j ON j.id = d.job_id
            WHERE d.id = ? AND j.owner_user_id = ?""",
        (document_id, user_id),
    ).fetchone()


def list_document_versions(conn: sqlite3.Connection, kind: str, job_id: int) -> list[sqlite3.Row]:
    """Version metadata (without content), newest first."""
    return conn.execute(
        f"""SELECT id, job_id, version, source_profile_id, created_at, origin, length(content_md) AS length
            FROM {_table(kind)} WHERE job_id = ? ORDER BY version DESC""",
        (job_id,),
    ).fetchall()

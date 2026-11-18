"""Guest workspaces of the live demo (DEMO_LIVE): one throwaway account per visitor, with the sample profile.

A guest gets a copy of the demo user's approved profile and search settings, may search, score and generate with the
real providers inside the demo's daily budget, and is deleted with everything it owns after `GUEST_TTL`.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import timedelta

from werkzeug.security import generate_password_hash

from core.errors import ApiError
from core.time_utils import utc_now, utc_now_iso

GUEST_PREFIX = "guest_"
GUEST_TTL = timedelta(hours=24)
DEFAULT_GUESTS_PER_DAY = 40
DEFAULT_GUESTS_PER_CLIENT = 5
GUESTS_FULL_MESSAGE = "The live demo has reached today's visitor limit. The sample workspace is still open."
CLIENT_LIMIT_MESSAGE = "You have started the live demo several times today. Try again tomorrow."
_USER_COLUMNS = "id, username, created_at, last_login_at, is_active, is_admin"
_PROFILE_COLUMNS = (
    "profile_version, source_bundle_json, master_profile_json, model_name, created_at, "
    "review_status, review_note, reviewed_at_utc"
)
# Rows that hang off a job; deleted before the job itself (foreign keys are enforced).
_JOB_TABLES = (
    "evaluations",
    "cover_letters",
    "generated_resumes",
    "applications",
    "failed_jobs",
    "generation_decisions",
    "job_triage",
)


def is_guest(user_row) -> bool:
    return user_row is not None and str(user_row["username"]).startswith(GUEST_PREFIX)


def _limit(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def guests_per_day() -> int:
    return _limit("DEMO_GUESTS_PER_DAY", DEFAULT_GUESTS_PER_DAY)


def guests_per_client() -> int:
    return _limit("DEMO_GUESTS_PER_CLIENT", DEFAULT_GUESTS_PER_CLIENT)


def client_key(secret: str, address: str | None) -> str:
    """A keyed hash of the visitor's address: enough to count starts per visitor without storing the address."""
    return hmac.new(str(secret).encode(), str(address or "unknown").encode(), hashlib.sha256).hexdigest()[:32]


def create_guest(conn: sqlite3.Connection, client: str) -> sqlite3.Row:
    """A new guest account holding a copy of the demo user's approved profile and search settings.

    `client` is `client_key(...)` of the caller; one client may start only a few guests per day.
    """
    purge_expired_guests(conn)
    since = (utc_now() - GUEST_TTL).isoformat()
    conn.execute("DELETE FROM guest_starts WHERE started_at_utc < ?", (since,))
    mine = conn.execute(
        "SELECT COUNT(*) FROM guest_starts WHERE client_key = ? AND started_at_utc >= ?", (client, since)
    ).fetchone()[0]
    if int(mine) >= guests_per_client():
        raise ApiError(429, 3005, CLIENT_LIMIT_MESSAGE)
    recent = conn.execute(
        "SELECT COUNT(*) FROM users WHERE username LIKE ? AND created_at >= ?", (GUEST_PREFIX + "%", since)
    ).fetchone()[0]
    if int(recent) >= guests_per_day():
        raise ApiError(429, 3005, GUESTS_FULL_MESSAGE)
    demo = conn.execute("SELECT id FROM users WHERE username = 'demo'").fetchone()
    profile = (
        conn.execute(
            f"SELECT {_PROFILE_COLUMNS} FROM candidate_profiles WHERE user_id = ? AND review_status = 'approved' "
            "ORDER BY id DESC LIMIT 1",
            (int(demo["id"]),),
        ).fetchone()
        if demo is not None
        else None
    )
    if profile is None:
        raise ApiError(503, 5003, "The demo workspace is not seeded.")

    now = utc_now_iso()
    conn.execute("INSERT INTO guest_starts (client_key, started_at_utc) VALUES (?, ?)", (client, now))
    username = GUEST_PREFIX + secrets.token_hex(8)
    conn.execute(
        "INSERT INTO users (username, password_hash, created_at, last_login_at, is_active, is_admin) "
        "VALUES (?, ?, ?, ?, 1, 0)",
        (username, generate_password_hash(secrets.token_urlsafe(32)), now, now),
    )
    guest = conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE username = ?", (username,)).fetchone()
    guest_id = int(guest["id"])
    conn.execute(
        f"INSERT INTO candidate_profiles (user_id, {_PROFILE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (guest_id, *tuple(profile)),
    )
    conn.execute(
        "INSERT INTO user_search_preferences (user_id, provider, params_json, created_at_utc, updated_at_utc) "
        "SELECT ?, provider, params_json, ?, ? FROM user_search_preferences WHERE user_id = ?",
        (guest_id, now, now, int(demo["id"])),
    )
    return guest


def purge_expired_guests(conn: sqlite3.Connection, ttl: timedelta = GUEST_TTL) -> int:
    """Delete guests older than `ttl` with everything they own; a guest with a task in flight waits for the next run."""
    cutoff = (utc_now() - ttl).isoformat()
    rows = conn.execute(
        "SELECT id FROM users WHERE username LIKE ? AND created_at < ? AND id NOT IN "
        "(SELECT owner_user_id FROM async_tasks WHERE state IN ('queued', 'running'))",
        (GUEST_PREFIX + "%", cutoff),
    ).fetchall()
    for row in rows:
        _delete_guest(conn, int(row["id"]))
    return len(rows)


def _delete_guest(conn: sqlite3.Connection, user_id: int) -> None:
    jobs = "SELECT id FROM jobs WHERE owner_user_id = ?"
    tasks = "SELECT task_id FROM async_tasks WHERE owner_user_id = ?"
    for table in _JOB_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE job_id IN ({jobs})", (user_id,))
    conn.execute("DELETE FROM jobs WHERE owner_user_id = ?", (user_id,))
    for table in ("task_events", "task_artifacts"):
        conn.execute(f"DELETE FROM {table} WHERE task_id IN ({tasks})", (user_id,))
    conn.execute("DELETE FROM async_tasks WHERE owner_user_id = ?", (user_id,))
    for table in ("candidate_profiles", "user_preferences", "user_search_preferences"):
        conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'api_usage_daily_subject'").fetchone():
        conn.execute("DELETE FROM api_usage_daily_subject WHERE subject = ?", (f"user:{user_id}",))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

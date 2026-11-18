"""Per-account sign-in throttling, shared by all worker processes through SQLite.

Keyed by username rather than IP: behind Cloudflare Tunnel every request arrives from the
tunnel container, so an IP limit would lock out everyone at once. Edge rate limits (see
docs/operations.md) cover high-volume attacks across many usernames.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from core.time_utils import utc_now

MAX_FAILURES = 10
WINDOW = timedelta(minutes=15)


def _key(username: str) -> str:
    return str(username or "").strip().lower()


def is_locked(conn: sqlite3.Connection, username: str) -> bool:
    cutoff = (utc_now() - WINDOW).isoformat()
    count = conn.execute(
        "SELECT COUNT(*) FROM login_failures WHERE username = ? AND failed_at_utc >= ?",
        (_key(username), cutoff),
    ).fetchone()[0]
    return int(count) >= MAX_FAILURES


def record_failure(conn: sqlite3.Connection, username: str) -> None:
    conn.execute(
        "INSERT INTO login_failures (username, failed_at_utc) VALUES (?, ?)",
        (_key(username), utc_now().isoformat()),
    )
    conn.execute("DELETE FROM login_failures WHERE failed_at_utc < ?", ((utc_now() - WINDOW).isoformat(),))


def clear_failures(conn: sqlite3.Connection, username: str) -> None:
    conn.execute("DELETE FROM login_failures WHERE username = ?", (_key(username),))

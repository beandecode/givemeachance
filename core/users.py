from __future__ import annotations

import logging
import os
import re
import secrets
import sqlite3
import uuid

from werkzeug.security import check_password_hash, generate_password_hash

from core.time_utils import utc_now_iso

_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(16))
_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def _normalize_username(username: str) -> str:
    return str(username or "").strip().lower()


def validate_username(username: str) -> str:
    normalized = _normalize_username(username)
    if not _USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("username must be 3-32 chars: letters, digits, _, -, .")
    return normalized


def validate_password(password: str) -> None:
    text = str(password or "")
    if len(text) < 8:
        raise ValueError("password must be at least 8 characters")


def ensure_default_demo_user(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, username, created_at, last_login_at, is_active, is_admin FROM users WHERE username = ?",
        ("demo",),
    ).fetchone()
    if row is not None:
        return row

    now = utc_now_iso()
    # OR IGNORE: concurrent first requests may race to create the demo row.
    conn.execute(
        """
        INSERT OR IGNORE INTO users (username, password_hash, created_at, last_login_at, is_active, is_admin)
        VALUES (?, ?, ?, ?, 1, 0)
        """,
        ("demo", generate_password_hash(secrets.token_urlsafe(32)), now, now),
    )
    return conn.execute(
        "SELECT id, username, created_at, last_login_at, is_active, is_admin FROM users WHERE username = ?",
        ("demo",),
    ).fetchone()


def ensure_admin_account(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Optionally create a bootstrap admin from environment variables.

    Required env vars:
    - ADMIN_BOOTSTRAP_USERNAME
    - ADMIN_BOOTSTRAP_PASSWORD

    Optional env var:
    - ADMIN_BOOTSTRAP_FORCE_RESET=true to reset the password on each startup.

    An existing non-admin account with the same username is promoted only with
    FORCE_RESET, which also replaces its password; otherwise anyone who registered
    that name first would silently become admin with their own password.
    """
    raw_username = str(os.getenv("ADMIN_BOOTSTRAP_USERNAME", "")).strip()
    raw_password = str(os.getenv("ADMIN_BOOTSTRAP_PASSWORD", ""))
    force_reset = str(os.getenv("ADMIN_BOOTSTRAP_FORCE_RESET", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }

    if not raw_username or not raw_password:
        return None

    username = validate_username(raw_username)
    validate_password(raw_password)

    now = utc_now_iso()
    password_hash = generate_password_hash(raw_password)

    # OR IGNORE: several gunicorn workers run this at startup concurrently.
    inserted = conn.execute(
        """
        INSERT OR IGNORE INTO users (username, password_hash, created_at, last_login_at, is_active, is_admin)
        VALUES (?, ?, ?, ?, 1, 1)
        """,
        (username, password_hash, now, now),
    ).rowcount

    if not inserted:
        existing = conn.execute(
            "SELECT id, is_admin FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if force_reset:
            conn.execute(
                "UPDATE users SET password_hash = ?, is_active = 1, is_admin = 1 WHERE id = ?",
                (password_hash, int(existing["id"])),
            )
        elif int(existing["is_admin"]) == 1:
            conn.execute("UPDATE users SET is_active = 1 WHERE id = ?", (int(existing["id"]),))
        else:
            logging.getLogger(__name__).warning(
                "Admin bootstrap skipped: '%s' is an existing non-admin account; "
                "set ADMIN_BOOTSTRAP_FORCE_RESET=true to promote it and reset its password.",
                username,
            )

    return conn.execute(
        "SELECT id, username, created_at, last_login_at, is_active, is_admin FROM users WHERE username = ?",
        (username,),
    ).fetchone()


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, username, created_at, last_login_at, is_active, is_admin FROM users WHERE id = ?",
        (int(user_id),),
    ).fetchone()


def create_user(conn: sqlite3.Connection, username: str, password: str) -> sqlite3.Row:
    normalized = validate_username(username)
    if normalized in {"demo", "system_owner"} or normalized.startswith("guest_"):  # guests: core/guest_service.py
        raise ValueError("username is reserved")
    validate_password(password)

    now = utc_now_iso()
    try:
        conn.execute(
            """
            INSERT INTO users (username, password_hash, created_at, last_login_at, is_active, is_admin)
            VALUES (?, ?, ?, ?, 1, 0)
            """,
            (normalized, generate_password_hash(password), now, now),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("username already exists") from exc
    return conn.execute(
        "SELECT id, username, created_at, last_login_at, is_active, is_admin FROM users WHERE username = ?",
        (normalized,),
    ).fetchone()


def authenticate_user(conn: sqlite3.Connection, username: str, password: str) -> sqlite3.Row | None:
    normalized = _normalize_username(username)
    row = conn.execute(
        "SELECT id, username, password_hash, created_at, last_login_at, is_active, is_admin"
        " FROM users WHERE username = ?",
        (normalized,),
    ).fetchone()
    if row is None:
        # Same hashing cost as a real check, so response time doesn't reveal which usernames exist.
        check_password_hash(_DUMMY_PASSWORD_HASH, str(password or ""))
        return None
    if int(row["is_active"]) != 1:
        return None
    if not check_password_hash(str(row["password_hash"]), str(password or "")):
        return None

    now = utc_now_iso()
    conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, int(row["id"])))
    return conn.execute(
        "SELECT id, username, created_at, last_login_at, is_active, is_admin FROM users WHERE id = ?",
        (int(row["id"]),),
    ).fetchone()


def ensure_system_owner_user(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM users WHERE username = ?", ("system_owner",)).fetchone()
    if row is not None:
        return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])

    now = utc_now_iso()
    conn.execute(
        """
        INSERT OR IGNORE INTO users (username, password_hash, created_at, last_login_at, is_active, is_admin)
        VALUES (?, ?, ?, NULL, 0, 0)
        """,
        ("system_owner", generate_password_hash(uuid.uuid4().hex), now),
    )
    row = conn.execute("SELECT id FROM users WHERE username = ?", ("system_owner",)).fetchone()
    if row is None:
        raise RuntimeError("failed to create system owner user")
    return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])

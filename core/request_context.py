from __future__ import annotations

import os
import sqlite3

from flask import session

from core.demo import demo_live_enabled, demo_mode_enabled
from core.guest_service import is_guest

# Re-export pure helpers for existing callers; workers import core.user_scope directly.
from core.user_scope import is_admin_user, profile_scope_user_id, quota_subject_for_user
from core.users import ensure_default_demo_user, get_user_by_id

__all__ = [
    "is_admin_user",
    "profile_scope_user_id",
    "quota_subject_for_user",
    "registration_open",
    "resolve_request_user",
]


def registration_open() -> bool:
    """Self-service sign-up is off unless REGISTRATION_MODE=open (personal deployment by default)."""
    return str(os.getenv("REGISTRATION_MODE", "closed")).strip().lower() == "open"


def resolve_request_user(conn: sqlite3.Connection, allow_demo_fallback: bool = True):
    session_user_id = session.get("user_id")
    if session_user_id is not None:
        try:
            user_row = get_user_by_id(conn, int(session_user_id))
            # A guest account only means something while the live demo is on.
            if user_row is not None and int(user_row["is_active"]) == 1:
                if not is_guest(user_row) or demo_live_enabled():
                    return user_row
        except (TypeError, ValueError):
            pass

    if allow_demo_fallback and demo_mode_enabled():
        demo_row = ensure_default_demo_user(conn)
        return demo_row

    return None

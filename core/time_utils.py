from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Return current UTC datetime in ISO-8601 format."""
    return utc_now().isoformat()


def utc_today_iso() -> str:
    """Return current UTC date in ISO-8601 format."""
    return utc_now().date().isoformat()


def utc_strftime(fmt: str) -> str:
    """Format current UTC datetime with strftime."""
    return utc_now().strftime(fmt)


def new_run_key(prefix: str = "run") -> str:
    """Human-readable timestamp with uniqueness across users and worker threads."""
    import uuid

    return f"{prefix}-{utc_strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:12]}"

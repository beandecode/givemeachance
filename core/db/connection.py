"""Runtime SQLite connections.

Every connection enforces foreign keys and waits up to BUSY_TIMEOUT_SECONDS for the
single writer lock. WAL journal mode is persistent and set once by `init_db`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

BUSY_TIMEOUT_SECONDS = 30


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Durable at every checkpoint and safe against corruption in WAL mode.
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def release_write_lock(conn: sqlite3.Connection) -> None:
    """Commit pending writes so SQLite's single writer lock is free.

    Call right before a slow external call (LLM, job board): holding the lock across it
    blocks every other writer. Pair with `begin_write` before writing the results.
    """
    if conn.in_transaction:
        conn.commit()


def begin_write(conn: sqlite3.Connection) -> None:
    """Start a write transaction now (BEGIN IMMEDIATE) so reads that follow see a stable state.

    Use when results of an external call are about to be written and their preconditions must be
    re-checked atomically with the write. The caller's `db_conn` block commits it.
    """
    release_write_lock(conn)
    conn.execute("BEGIN IMMEDIATE")


@contextmanager
def db_conn(db_path: str) -> Iterator[sqlite3.Connection]:
    """One unit of work: commit on success, roll back on error, always close."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

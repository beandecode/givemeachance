"""Schema creation and numbered migrations.

`init_db` applies every migration in MIGRATIONS that is not yet recorded in
`schema_migrations`, each in its own transaction, with foreign keys disabled while
the schema changes (SQLite requires that for table rebuilds) and a
`foreign_key_check` before commit. An existing database with pending migrations is
backed up first. Add new schema changes as a new entry at the end of MIGRATIONS;
never edit an applied migration.
"""

from __future__ import annotations

import fcntl
import logging
import secrets
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from werkzeug.security import generate_password_hash

from core.time_utils import utc_now_iso
from core.users import ensure_system_owner_user

logger = logging.getLogger(__name__)

OWNER_SCOPED_JOBS_MIGRATION_ID = "20260522_owner_scoped_jobs"


@contextmanager
def _database_init_lock(db_path: Path) -> Iterator[None]:
    lock_path = db_path.parent / f"{db_path.name}.init.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at_utc TEXT NOT NULL
        )
        """
    )
    # Databases created by an early, uncommitted version name the column `applied_at`.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(schema_migrations)")}
    if "applied_at_utc" not in columns and "applied_at" in columns:
        conn.execute("ALTER TABLE schema_migrations RENAME COLUMN applied_at TO applied_at_utc")


def _is_migration_applied(conn: sqlite3.Connection, migration_id: str) -> bool:
    row = conn.execute(
        "SELECT migration_id FROM schema_migrations WHERE migration_id = ?",
        (str(migration_id),),
    ).fetchone()
    return row is not None


def _record_migration(conn: sqlite3.Connection, migration_id: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (migration_id, applied_at_utc)
        VALUES (?, ?)
        """,
        (str(migration_id), utc_now_iso()),
    )


def _jobs_table_is_owner_scoped(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'jobs'",
    ).fetchone()
    if row is None:
        return False
    sql = str(row["sql"] if isinstance(row, sqlite3.Row) else row[0])
    normalized = " ".join(sql.lower().replace("\n", " ").split())
    return "unique(source, source_job_id, owner_user_id)" in normalized


def _create_jobs_table_sql(table_name: str = "jobs") -> str:
    return f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                salary_min INTEGER,
                salary_max INTEGER,
                description TEXT NOT NULL,
                description_hash TEXT NOT NULL,
                posted_date TEXT NOT NULL,
                url TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                owner_user_id INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(source, source_job_id, owner_user_id)
            )
            """


def _rebuild_jobs_for_owner_scoped_unique(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS jobs_owner_scoped_new")
    conn.execute(_create_jobs_table_sql("jobs_owner_scoped_new"))
    conn.execute(
        """
        INSERT INTO jobs_owner_scoped_new (
            id, source, source_job_id, title, company, location, salary_min, salary_max,
            description, description_hash, posted_date, url, raw_payload, owner_user_id, created_at
        )
        SELECT
            id, source, source_job_id, title, company, location, salary_min, salary_max,
            description, description_hash, posted_date, url, raw_payload, owner_user_id, created_at
        FROM jobs
        """
    )
    conn.execute("DROP TABLE jobs")
    conn.execute("ALTER TABLE jobs_owner_scoped_new RENAME TO jobs")


def _owner_scoped_jobs(conn: sqlite3.Connection) -> None:
    """Assign legacy ownerless jobs to `system_owner` and make job uniqueness per owner."""
    system_owner_id = ensure_system_owner_user(conn)
    conn.execute(
        "UPDATE jobs SET owner_user_id = ? WHERE owner_user_id IS NULL",
        (system_owner_id,),
    )
    if not _jobs_table_is_owner_scoped(conn):
        _rebuild_jobs_for_owner_scoped_unique(conn)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl_fragment: str) -> None:
    existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_fragment}")


def _baseline_schema(conn: sqlite3.Connection) -> None:
    """Schema as of 2026-10. Idempotent so it also upgrades databases created before migrations were numbered."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_admin INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    conn.execute(_create_jobs_table_sql())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            match_score INTEGER NOT NULL,
            strengths TEXT NOT NULL,
            gaps TEXT NOT NULL,
            fit_reason TEXT NOT NULL,
            should_apply INTEGER NOT NULL,
            total_score INTEGER,
            dimension_scores_json TEXT NOT NULL DEFAULT '{}',
            match_reasons TEXT NOT NULL DEFAULT '[]',
            risk_flags TEXT NOT NULL DEFAULT '[]',
            recommendation_level TEXT NOT NULL DEFAULT 'maybe',
            confidence_level TEXT NOT NULL DEFAULT 'medium',
            missing_information TEXT NOT NULL DEFAULT '[]',
            source_profile_id INTEGER,
            source_profile_version INTEGER,
            model_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id),
            FOREIGN KEY(source_profile_id) REFERENCES candidate_profiles(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cover_letters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            content_md TEXT NOT NULL,
            source_profile_id INTEGER,
            evidence_map_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(job_id, version),
            FOREIGN KEY(job_id) REFERENCES jobs(id),
            FOREIGN KEY(source_profile_id) REFERENCES candidate_profiles(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            status TEXT NOT NULL,
            status_note TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_key TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS failed_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_key TEXT NOT NULL,
            job_id INTEGER,
            stage TEXT NOT NULL,
            error_message TEXT NOT NULL,
            retry_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS generation_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            viewed_match_at TEXT,
            decision_generate_resume INTEGER NOT NULL DEFAULT 0,
            decision_generate_cover_letter INTEGER NOT NULL DEFAULT 0,
            decided_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_version INTEGER NOT NULL,
            user_id INTEGER,
            source_bundle_json TEXT NOT NULL,
            master_profile_json TEXT NOT NULL,
            model_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'pending',
            review_note TEXT,
            reviewed_at_utc TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS generated_resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            content_md TEXT NOT NULL,
            source_profile_id INTEGER,
            evidence_map_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(job_id, version),
            FOREIGN KEY(job_id) REFERENCES jobs(id),
            FOREIGN KEY(source_profile_id) REFERENCES candidate_profiles(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS async_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL UNIQUE,
            task_type TEXT NOT NULL,
            owner_user_id INTEGER NOT NULL,
            state TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT,
            result_ref TEXT,
            error_code INTEGER,
            error_message_safe TEXT,
            progress_percent INTEGER NOT NULL DEFAULT 0,
            progress_stage TEXT NOT NULL DEFAULT 'queued',
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            correlation_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            started_at_utc TEXT,
            finished_at_utc TEXT,
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            stage_name TEXT NOT NULL,
            progress_percent INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL,
            delta_text TEXT,
            correlation_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES async_tasks(task_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            ref_key TEXT,
            content_json TEXT NOT NULL DEFAULT '{}',
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES async_tasks(task_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_search_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL DEFAULT 'adzuna',
            params_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(user_id, provider),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_async_tasks_owner_state ON async_tasks(owner_user_id, state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task_id_id ON task_events(task_id, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_artifacts_task_id ON task_artifacts(task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_search_preferences_user ON user_search_preferences(user_id)")
    _ensure_column(conn, "cover_letters", "source_profile_id", "INTEGER")
    _ensure_column(conn, "cover_letters", "evidence_map_json", "TEXT NOT NULL DEFAULT '{}' ")
    _ensure_column(conn, "generated_resumes", "evidence_map_json", "TEXT NOT NULL DEFAULT '{}' ")
    _ensure_column(conn, "users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "jobs", "owner_user_id", "INTEGER")
    _ensure_column(conn, "evaluations", "total_score", "INTEGER")
    _ensure_column(conn, "evaluations", "dimension_scores_json", "TEXT NOT NULL DEFAULT '{}' ")
    _ensure_column(conn, "evaluations", "match_reasons", "TEXT NOT NULL DEFAULT '[]' ")
    _ensure_column(conn, "evaluations", "risk_flags", "TEXT NOT NULL DEFAULT '[]' ")
    _ensure_column(conn, "evaluations", "recommendation_level", "TEXT NOT NULL DEFAULT 'maybe' ")
    _ensure_column(conn, "evaluations", "confidence_level", "TEXT NOT NULL DEFAULT 'medium' ")
    _ensure_column(conn, "evaluations", "missing_information", "TEXT NOT NULL DEFAULT '[]' ")
    _ensure_column(conn, "evaluations", "source_profile_id", "INTEGER")
    _ensure_column(conn, "evaluations", "source_profile_version", "INTEGER")
    _ensure_column(conn, "candidate_profiles", "user_id", "INTEGER")
    _ensure_column(conn, "candidate_profiles", "review_status", "TEXT NOT NULL DEFAULT 'pending' ")
    _ensure_column(conn, "candidate_profiles", "review_note", "TEXT")
    _ensure_column(conn, "candidate_profiles", "reviewed_at_utc", "TEXT")
    _ensure_column(conn, "async_tasks", "payload_json", "TEXT NOT NULL DEFAULT '{}' ")
    _ensure_column(conn, "async_tasks", "result_json", "TEXT")
    _ensure_column(conn, "async_tasks", "result_ref", "TEXT")
    _ensure_column(conn, "async_tasks", "error_code", "INTEGER")
    _ensure_column(conn, "async_tasks", "error_message_safe", "TEXT")
    _ensure_column(conn, "async_tasks", "progress_percent", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "async_tasks", "progress_stage", "TEXT NOT NULL DEFAULT 'queued' ")
    _ensure_column(conn, "async_tasks", "cancel_requested", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "async_tasks", "correlation_id", "TEXT NOT NULL DEFAULT '' ")
    _ensure_column(conn, "async_tasks", "created_at_utc", "TEXT")
    _ensure_column(conn, "async_tasks", "started_at_utc", "TEXT")
    _ensure_column(conn, "async_tasks", "finished_at_utc", "TEXT")


def _query_indexes(conn: sqlite3.Connection) -> None:
    """Indexes for the per-owner lists, task capacity checks and failed-job lookups."""
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_jobs_owner_id ON jobs(owner_user_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_candidate_profiles_user_id ON candidate_profiles(user_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_async_tasks_state ON async_tasks(state)",
        "CREATE INDEX IF NOT EXISTS idx_async_tasks_owner_id ON async_tasks(owner_user_id, id)",
        "CREATE INDEX IF NOT EXISTS idx_failed_jobs_job_id ON failed_jobs(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_failed_jobs_run_key ON failed_jobs(run_key)",
        "CREATE INDEX IF NOT EXISTS idx_failed_jobs_unresolved ON failed_jobs(id) WHERE resolved_at IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_run_key ON pipeline_runs(run_key)",
    ):
        conn.execute(statement)


def _task_heartbeat(conn: sqlite3.Connection) -> None:
    """Liveness of running tasks, so tasks orphaned by a crash or restart can be recovered."""
    _ensure_column(conn, "async_tasks", "heartbeat_at_utc", "TEXT")


def _auth_hardening(conn: sqlite3.Connection) -> None:
    """Sign-in throttling table; the demo account gets an unguessable password (it was a public default)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS login_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            failed_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_login_failures_username ON login_failures(username, failed_at_utc)")
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE username = 'demo'",
        (generate_password_hash(secrets.token_urlsafe(32)),),
    )


def _jobs_archive_and_document_origin(conn: sqlite3.Connection) -> None:
    """Hide jobs from the default list without deleting them; tell user edits apart from generated versions."""
    _ensure_column(conn, "jobs", "archived_at", "TEXT")
    _ensure_column(conn, "generated_resumes", "origin", "TEXT NOT NULL DEFAULT 'generated'")
    _ensure_column(conn, "cover_letters", "origin", "TEXT NOT NULL DEFAULT 'generated'")


def _evaluation_profile_fingerprint(conn: sqlite3.Connection) -> None:
    """Remember what the scorer saw, so profile edits that do not change it keep the evaluation valid."""
    _ensure_column(conn, "evaluations", "source_profile_fingerprint", "TEXT")


def _evaluation_prompt_version(conn: sqlite3.Connection) -> None:
    """Record which scoring prompt produced an evaluation (v1 rows stay NULL)."""
    _ensure_column(conn, "evaluations", "prompt_version", "TEXT")


def _triage_and_preferences(conn: sqlite3.Connection) -> None:
    """Swipe decisions per job (separate from application stages) and typed per-user UI preferences."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS job_triage (
            user_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('skipped', 'waitlisted', 'accepted')),
            generate TEXT CHECK (generate IN ('resume', 'resume_and_cover_letter')),
            decided_at TEXT NOT NULL,
            PRIMARY KEY (user_id, job_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_triage_job ON job_triage(job_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value_json TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )


def _application_follow_up(conn: sqlite3.Connection) -> None:
    """A date to follow up on an application (the guided journey, ADR-015)."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(applications)")}
    if "follow_up_at" not in columns:
        conn.execute("ALTER TABLE applications ADD COLUMN follow_up_at TEXT")


def _relevance_and_swipe_reasons(conn: sqlite3.Connection) -> None:
    """A cheap relevance score per job and an optional reason for each swipe (ADR-017)."""
    if "relevance" not in {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}:
        conn.execute("ALTER TABLE jobs ADD COLUMN relevance INTEGER")
    if "reason" not in {row[1] for row in conn.execute("PRAGMA table_info(job_triage)")}:
        conn.execute("ALTER TABLE job_triage ADD COLUMN reason TEXT")


def _guest_starts(conn: sqlite3.Connection) -> None:
    """Live demo: when a guest workspace was started from which (hashed) address, to limit starts per visitor."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS guest_starts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_key TEXT NOT NULL,
            started_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_guest_starts_client ON guest_starts(client_key, started_at_utc)")


Migration = tuple[str, Callable[[sqlite3.Connection], None]]

MIGRATIONS: list[Migration] = [
    ("0001_baseline_schema", _baseline_schema),
    (OWNER_SCOPED_JOBS_MIGRATION_ID, _owner_scoped_jobs),
    ("0003_query_indexes", _query_indexes),
    ("0004_task_heartbeat", _task_heartbeat),
    ("0005_auth_hardening", _auth_hardening),
    ("0006_jobs_archive_and_document_origin", _jobs_archive_and_document_origin),
    ("0007_evaluation_profile_fingerprint", _evaluation_profile_fingerprint),
    ("0008_evaluation_prompt_version", _evaluation_prompt_version),
    ("0009_triage_and_preferences", _triage_and_preferences),
    ("0010_application_follow_up", _application_follow_up),
    ("0011_relevance_and_swipe_reasons", _relevance_and_swipe_reasons),
    ("0012_guest_starts", _guest_starts),
]


class MigrationError(RuntimeError):
    pass


def _has_user_data(conn: sqlite3.Connection) -> bool:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone() is None:
        return False
    return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def _backup(conn: sqlite3.Connection, db_path: Path) -> Path:
    stamp = utc_now_iso().replace(":", "").replace("-", "").split(".")[0].split("+")[0]
    backup_path = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    with sqlite3.connect(backup_path) as target:
        conn.backup(target)
    target.close()
    return backup_path


def init_db(db_path: str) -> None:
    """Create or upgrade the schema; safe to call from several processes at startup."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with _database_init_lock(path):
        conn = sqlite3.connect(path, isolation_level=None)  # explicit BEGIN/COMMIT below
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("PRAGMA journal_mode = WAL")
            _ensure_schema_migrations_table(conn)
            pending = [(mid, apply) for mid, apply in MIGRATIONS if not _is_migration_applied(conn, mid)]
            if pending and _has_user_data(conn):
                logger.info("Backed up database to %s before migrating", _backup(conn, path))
            for migration_id, apply in pending:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    apply(conn)
                    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                    if violations:
                        raise MigrationError(
                            f"{migration_id} would leave {len(violations)} foreign key violation(s), "
                            f"first: {tuple(violations[0])}"
                        )
                    _record_migration(conn, migration_id)
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
                logger.info("Applied database migration %s", migration_id)
        finally:
            conn.close()

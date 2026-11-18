import sqlite3

import pytest

from core.db import db_conn, init_db, migrations


def _applied(db_path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[0] for row in conn.execute("SELECT migration_id FROM schema_migrations")}


def test_fresh_database_gets_wal_all_migrations_and_no_backup(tmp_path):
    db_path = tmp_path / "fresh.db"

    init_db(str(db_path))

    assert _applied(db_path) == {migration_id for migration_id, _ in migrations.MIGRATIONS}
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert list(tmp_path.glob("fresh.db.bak-*")) == []


def test_runtime_connections_enforce_foreign_keys(tmp_path):
    db_path = str(tmp_path / "fk.db")
    init_db(db_path)

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"), db_conn(db_path) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        conn.execute(
            "INSERT INTO applications (job_id, status, status_note, updated_at) VALUES (999, 'draft', '', 'now')"
        )


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "twice.db"
    init_db(str(db_path))
    with db_conn(str(db_path)) as conn:
        conn.execute("INSERT INTO users (username, password_hash, created_at) VALUES ('someone', 'x', 'now')")

    init_db(str(db_path))

    assert list(tmp_path.glob("twice.db.bak-*")) == []


def _create_legacy_database(db_path) -> None:
    """Shape of a pre-migration database: global job uniqueness and a child table referencing jobs."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, created_at TEXT NOT NULL, last_login_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1, is_admin INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, source_job_id TEXT NOT NULL,
                title TEXT NOT NULL, company TEXT NOT NULL, location TEXT NOT NULL,
                salary_min INTEGER, salary_max INTEGER, description TEXT NOT NULL,
                description_hash TEXT NOT NULL, posted_date TEXT NOT NULL, url TEXT NOT NULL,
                raw_payload TEXT NOT NULL, owner_user_id INTEGER, created_at TEXT NOT NULL,
                UNIQUE(source, source_job_id)
            );
            CREATE TABLE evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL UNIQUE,
                match_score INTEGER NOT NULL, strengths TEXT NOT NULL, gaps TEXT NOT NULL,
                fit_reason TEXT NOT NULL, should_apply INTEGER NOT NULL, model_name TEXT NOT NULL,
                created_at TEXT NOT NULL, FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            INSERT INTO users (username, password_hash, created_at) VALUES ('owner', 'x', 'now');
            INSERT INTO jobs (source, source_job_id, title, company, location, description, description_hash,
                              posted_date, url, raw_payload, owner_user_id, created_at)
            VALUES ('adzuna', 'legacy-1', 'Backend Engineer', 'Acme', 'Toronto', 'Build APIs', 'h',
                    '2026-05-22', 'https://example.com', '{}', NULL, '2026-05-22T00:00:00Z');
            INSERT INTO evaluations (job_id, match_score, strengths, gaps, fit_reason, should_apply,
                                     model_name, created_at)
            VALUES (1, 80, '[]', '[]', 'fit', 1, 'mock', 'now');
            """
        )


def test_legacy_database_is_backed_up_and_upgraded_without_breaking_references(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_database(db_path)

    init_db(str(db_path))

    backups = list(tmp_path.glob("legacy.db.bak-*"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT job_id, match_score FROM evaluations").fetchall() == [(1, 80)]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(evaluations)")}
        assert {"total_score", "source_profile_id", "recommendation_level"} <= columns
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert "idx_jobs_owner_id" in indexes
    assert _applied(db_path) == {migration_id for migration_id, _ in migrations.MIGRATIONS}


def test_failed_migration_rolls_back_and_is_not_recorded(tmp_path, monkeypatch):
    db_path = tmp_path / "broken.db"
    init_db(str(db_path))

    def orphan_row(conn):
        conn.execute("CREATE TABLE scratch_marker (id INTEGER)")
        conn.execute(
            "INSERT INTO applications (job_id, status, status_note, updated_at) VALUES (999, 'draft', '', 'now')"
        )

    monkeypatch.setattr(migrations, "MIGRATIONS", [*migrations.MIGRATIONS, ("9999_orphan", orphan_row)])

    with pytest.raises(migrations.MigrationError, match="9999_orphan"):
        init_db(str(db_path))

    assert "9999_orphan" not in _applied(db_path)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'scratch_marker'").fetchone() is None


def test_legacy_schema_migrations_column_name_is_upgraded(tmp_path):
    db_path = tmp_path / "early.db"
    _create_legacy_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE schema_migrations (migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_migrations VALUES ('001_owner_scoped_jobs_unique', '2026-05-21T22:41:18Z')")

    init_db(str(db_path))

    applied = _applied(db_path)
    assert "001_owner_scoped_jobs_unique" in applied
    assert {migration_id for migration_id, _ in migrations.MIGRATIONS} <= applied

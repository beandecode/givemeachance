import sqlite3

from core.config import load_settings
from core.db import OWNER_SCOPED_JOBS_MIGRATION_ID, db_conn, init_db
from core.persistence import job_visibility_clause, load_scoped_job
from core.repositories.jobs import insert_job_if_new
from core.schemas import JobRecord
from core.users import create_user


def _insert_job(conn, source_job_id: str, owner_user_id: int | None):
    conn.execute(
        """
        INSERT INTO jobs (
            source,
            source_job_id,
            title,
            company,
            location,
            salary_min,
            salary_max,
            description,
            description_hash,
            posted_date,
            url,
            raw_payload,
            owner_user_id,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            "test",
            source_job_id,
            "Backend Engineer",
            "Acme",
            "Toronto",
            None,
            None,
            "Build APIs",
            f"hash-{source_job_id}",
            "2026-04-17",
            f"https://example.com/{source_job_id}",
            "{}",
            owner_user_id,
        ),
    )


def test_job_visibility_clause_for_admin_and_user():
    admin = {"id": 1, "is_admin": 1}
    user = {"id": 2, "is_admin": 0}

    admin_sql, admin_args = job_visibility_clause(admin, alias="j")
    user_sql, user_args = job_visibility_clause(user, alias="j")
    none_sql, none_args = job_visibility_clause(None, alias="j")

    assert admin_sql == "1=1"
    assert admin_args == ()
    assert user_sql == "j.owner_user_id = ?"
    assert user_args == (2,)
    assert none_sql == "j.id = -1"
    assert none_args == ()


def test_load_scoped_job_enforces_owner_visibility():
    settings = load_settings()
    init_db(settings.app.db_path)

    with db_conn(settings.app.db_path) as conn:
        user_a = create_user(conn, username="owner_a", password="password123")
        user_b = create_user(conn, username="owner_b", password="password123")

        _insert_job(conn, "job-a", owner_user_id=int(user_a["id"]))
        _insert_job(conn, "job-b", owner_user_id=int(user_b["id"]))

        row_a = conn.execute("SELECT id FROM jobs WHERE source_job_id = ?", ("job-a",)).fetchone()
        row_b = conn.execute("SELECT id FROM jobs WHERE source_job_id = ?", ("job-b",)).fetchone()

        admin_user = {"id": 999, "is_admin": 1}
        scoped_a = {"id": int(user_a["id"]), "is_admin": 0}
        scoped_b = {"id": int(user_b["id"]), "is_admin": 0}

        assert load_scoped_job(conn, int(row_a["id"]), admin_user) is not None
        assert load_scoped_job(conn, int(row_b["id"]), admin_user) is not None

        assert load_scoped_job(conn, int(row_a["id"]), scoped_a) is not None
        assert load_scoped_job(conn, int(row_b["id"]), scoped_a) is None

        assert load_scoped_job(conn, int(row_b["id"]), scoped_b) is not None
        assert load_scoped_job(conn, int(row_a["id"]), scoped_b) is None


def test_insert_job_if_new_allows_same_external_job_for_different_owners():
    settings = load_settings()
    init_db(settings.app.db_path)

    job = JobRecord.model_validate(
        {
            "id": "same-external-id",
            "title": "Backend Engineer",
            "company": "Acme",
            "location": "Toronto",
            "salary_min": None,
            "salary_max": None,
            "description": "Build APIs",
            "posted_date": "2026-05-22",
            "source": "adzuna",
            "url": "https://example.com/job",
        }
    )

    with db_conn(settings.app.db_path) as conn:
        user_a = create_user(conn, username="same_job_owner_a", password="password123")
        user_b = create_user(conn, username="same_job_owner_b", password="password123")

        job_a = insert_job_if_new(
            conn, job, description_hash="hash-same", raw_payload="{}", owner_user_id=int(user_a["id"])
        )
        job_b = insert_job_if_new(
            conn, job, description_hash="hash-same", raw_payload="{}", owner_user_id=int(user_b["id"])
        )
        duplicate_a = insert_job_if_new(
            conn,
            job,
            description_hash="hash-same",
            raw_payload="{}",
            owner_user_id=int(user_a["id"]),
        )

    assert job_a is not None
    assert job_b is not None
    assert int(job_a) != int(job_b)
    assert duplicate_a is None


def test_owner_scoped_jobs_migration_backfills_legacy_ownerless_jobs(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
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
        conn.execute(
            """
            CREATE TABLE jobs (
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
                UNIQUE(source, source_job_id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO jobs (
                source, source_job_id, title, company, location, salary_min, salary_max,
                description, description_hash, posted_date, url, raw_payload, owner_user_id, created_at
            ) VALUES ('adzuna', 'legacy-1', 'Backend Engineer', 'Acme', 'Toronto', NULL, NULL,
                      'Build APIs', 'hash-legacy', '2026-05-22', 'https://example.com', '{}', NULL,
                      '2026-05-22T00:00:00Z')
            """
        )
        conn.commit()

    init_db(str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'jobs'",
        ).fetchone()["sql"]
        job = conn.execute("SELECT owner_user_id FROM jobs WHERE source_job_id = 'legacy-1'").fetchone()
        system_owner = conn.execute("SELECT id, is_active FROM users WHERE username = 'system_owner'").fetchone()
        migration = conn.execute(
            "SELECT migration_id FROM schema_migrations WHERE migration_id = ?",
            (OWNER_SCOPED_JOBS_MIGRATION_ID,),
        ).fetchone()

    assert "UNIQUE(source, source_job_id, owner_user_id)" in table_sql
    assert system_owner is not None
    assert int(system_owner["is_active"]) == 0
    assert int(job["owner_user_id"]) == int(system_owner["id"])
    assert migration is not None

"""Job postings and their evaluations."""

from __future__ import annotations

import json
import sqlite3

from core.schemas import EvaluationResult, JobRecord
from core.time_utils import utc_now_iso
from core.users import ensure_system_owner_user


def _weak_duplicate_id(
    conn: sqlite3.Connection, job: JobRecord, description_hash: str, owner_user_id: int | None
) -> int | None:
    """The same posting (title, company, text) this owner saved in the last 7 days, if any."""
    normalized_title = " ".join(job.title.lower().split())
    normalized_company = " ".join(job.company.lower().split())
    row = conn.execute(
        """
        SELECT id
        FROM jobs
        WHERE lower(trim(title)) = ?
          AND lower(trim(company)) = ?
          AND description_hash = ?
                    AND ((owner_user_id IS NULL AND ? IS NULL) OR owner_user_id = ?)
          AND created_at >= datetime('now', '-7 day')
        LIMIT 1
        """,
        (normalized_title, normalized_company, description_hash, owner_user_id, owner_user_id),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def job_already_saved(conn: sqlite3.Connection, job: JobRecord, description_hash: str, owner_user_id: int) -> bool:
    """Read-only twin of `insert_job_if_new`'s duplicate rules, so callers can skip a posting before counting it."""
    if _weak_duplicate_id(conn, job, description_hash, owner_user_id) is not None:
        return True
    return (
        conn.execute(
            "SELECT 1 FROM jobs WHERE source = ? AND source_job_id = ? AND owner_user_id = ?",
            (job.source, job.external_id, owner_user_id),
        ).fetchone()
        is not None
    )


def insert_job_if_new(
    conn: sqlite3.Connection,
    job: JobRecord,
    description_hash: str,
    raw_payload: str,
    owner_user_id: int | None = None,
) -> int | None:
    """Insert job if not already present; return inserted row id, or None if duplicate."""
    if owner_user_id is None:
        owner_user_id = ensure_system_owner_user(conn)

    if _weak_duplicate_id(conn, job, description_hash, owner_user_id) is not None:
        return None

    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO jobs (
            source, source_job_id, title, company, location, salary_min, salary_max,
            description, description_hash, posted_date, url, raw_payload, owner_user_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job.source,
            job.external_id,
            job.title,
            job.company,
            job.location,
            job.salary_min,
            job.salary_max,
            job.description,
            description_hash,
            job.posted_date,
            job.url,
            raw_payload,
            owner_user_id,
            utc_now_iso(),
        ),
    )

    if cursor.rowcount == 0:
        return None

    row = conn.execute(
        """
        SELECT id
        FROM jobs
        WHERE source = ?
          AND source_job_id = ?
          AND ((owner_user_id IS NULL AND ? IS NULL) OR owner_user_id = ?)
        """,
        (job.source, job.external_id, owner_user_id, owner_user_id),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def insert_evaluation(
    conn: sqlite3.Connection,
    job_id: int,
    evaluation: EvaluationResult,
    source_profile_id: int | None = None,
    source_profile_version: int | None = None,
    source_profile_fingerprint: str | None = None,
    prompt_version: str | None = None,
) -> None:
    """Upsert evaluation result for a job."""
    conn.execute(
        """
        INSERT INTO evaluations (
            job_id, match_score, strengths, gaps, fit_reason, should_apply,
            total_score, dimension_scores_json, match_reasons, risk_flags,
            recommendation_level, confidence_level, missing_information,
            source_profile_id, source_profile_version, source_profile_fingerprint,
            model_name, prompt_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            match_score=excluded.match_score,
            strengths=excluded.strengths,
            gaps=excluded.gaps,
            fit_reason=excluded.fit_reason,
            should_apply=excluded.should_apply,
            total_score=excluded.total_score,
            dimension_scores_json=excluded.dimension_scores_json,
            match_reasons=excluded.match_reasons,
            risk_flags=excluded.risk_flags,
            recommendation_level=excluded.recommendation_level,
            confidence_level=excluded.confidence_level,
            missing_information=excluded.missing_information,
            source_profile_id=excluded.source_profile_id,
            source_profile_version=excluded.source_profile_version,
            source_profile_fingerprint=excluded.source_profile_fingerprint,
            model_name=excluded.model_name,
            prompt_version=excluded.prompt_version,
            created_at=excluded.created_at
        """,
        (
            job_id,
            evaluation.match_score,
            json.dumps(evaluation.strengths, ensure_ascii=False),
            json.dumps(evaluation.gaps, ensure_ascii=False),
            evaluation.fit_reason,
            int(evaluation.should_apply),
            evaluation.total_score,
            json.dumps(evaluation.dimension_scores, ensure_ascii=False),
            json.dumps(evaluation.match_reasons, ensure_ascii=False),
            json.dumps(evaluation.risk_flags, ensure_ascii=False),
            evaluation.recommendation_level,
            evaluation.confidence,
            json.dumps(evaluation.missing_information, ensure_ascii=False),
            source_profile_id,
            source_profile_version,
            source_profile_fingerprint,
            evaluation.model_name,
            prompt_version,
            utc_now_iso(),
        ),
    )
    # Acknowledgement and generation choices apply to the report the user saw.
    # A new report (even with the same profile) requires a fresh decision.
    conn.execute(
        """UPDATE generation_decisions
           SET viewed_match_at = NULL, decision_generate_resume = 0,
               decision_generate_cover_letter = 0, updated_at = ?
           WHERE job_id = ?""",
        (utc_now_iso(), job_id),
    )

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from adapters.llm import get_llm
from core.db.connection import release_write_lock
from core.errors import QuotaExhaustedError, UserFacingError, failure_summary
from core.evaluation_profile import evaluation_projection, profile_fingerprint
from core.job_fulltext import fetch_full_description
from core.job_text import description_hash, is_description_snippet
from core.repositories.jobs import insert_evaluation
from core.repositories.profiles import get_latest_candidate_profile
from core.repositories.runs import log_failed_job
from core.schemas import JobRecord, Settings

logger = logging.getLogger(__name__)


def run_evaluation(
    conn,
    settings: Settings,
    resume: dict,
    target_job_ids: list[int],
    run_key: str,
    profile_row=None,
    force_profile_usage: bool = False,
    quota_subject: str | None = None,
    profile_user_id: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Evaluate jobs and persist structured scoring results.

    Stops at the first exhausted daily quota (every later call would fail the same way); the jobs not tried are
    returned in `not_attempted_job_ids`. A job known only from the job board's short preview is never scored: its full
    text is fetched first, and when that fails it is left unscored in `needs_description_job_ids`.
    `on_progress(done, total)` runs after each job with the write lock released.
    """
    evaluator = get_llm(settings, quota_subject=quota_subject)

    selected_profile_row = profile_row
    if (
        selected_profile_row is None
        and profile_user_id is not None
        and (settings.llm.fullstack_enabled or force_profile_usage or settings.llm.provider != "mock_gemini")
    ):
        selected_profile_row = get_latest_candidate_profile(conn, user_id=profile_user_id)

    effective_resume = resume
    source_profile_id: int | None = None
    source_profile_version: int | None = None
    profile_fp: str | None = None
    if selected_profile_row is not None:
        try:
            master_profile = json.loads(str(selected_profile_row["master_profile_json"] or "{}"))
            effective_resume = evaluation_projection(master_profile)
            profile_fp = profile_fingerprint(master_profile)
            source_profile_id = int(selected_profile_row["id"])
            source_profile_version = int(selected_profile_row["profile_version"])
        except (json.JSONDecodeError, TypeError, ValueError):
            effective_resume = resume
            source_profile_id = None
            source_profile_version = None
            profile_fp = None

    evaluated = 0
    failed_job_ids: list[int] = []
    not_attempted_job_ids: list[int] = []
    needs_description_job_ids: list[int] = []
    for position, job_id in enumerate(target_job_ids):
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            continue
        if is_description_snippet(row["source"], row["description"]):
            release_write_lock(conn)  # web request
            full = fetch_full_description(str(row["url"] or ""), str(row["description"] or ""))
            if full is None:
                needs_description_job_ids.append(job_id)
                continue
            conn.execute(
                "UPDATE jobs SET description = ?, description_hash = ? WHERE id = ?",
                (full, description_hash(row["title"], row["company"], full), job_id),
            )
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

        # Convert row data to a validated schema object to keep the interface
        # consistent with real provider payload handling.
        job = JobRecord.model_validate(
            {
                "id": row["source_job_id"],
                "title": row["title"],
                "company": row["company"],
                "location": row["location"],
                "salary_min": row["salary_min"],
                "salary_max": row["salary_max"],
                "description": row["description"],
                "posted_date": row["posted_date"],
                "source": row["source"],
                "url": row["url"],
            }
        )

        try:
            release_write_lock(conn)  # LLM call; previous results are committed first
            evaluation = evaluator.evaluate(
                resume=effective_resume,
                job=job,
            )
            insert_evaluation(
                conn,
                job_id,
                evaluation,
                source_profile_id=source_profile_id,
                source_profile_version=source_profile_version,
                source_profile_fingerprint=profile_fp,
                prompt_version=settings.llm.prompt_version,
            )
            evaluated += 1
            if on_progress is not None:
                release_write_lock(conn)  # progress is written on its own connection
                on_progress(evaluated + len(failed_job_ids), len(target_job_ids))
        except QuotaExhaustedError as error:
            log_failed_job(conn, run_key=run_key, stage="evaluate", job_id=job_id, error_message=failure_summary(error))
            not_attempted_job_ids = list(target_job_ids[position:])
            break
        except Exception as error:
            if not isinstance(error, UserFacingError):
                logger.exception("Evaluation of job %s failed (run_key=%s)", job_id, run_key)
            failed_job_ids.append(job_id)
            log_failed_job(
                conn,
                run_key=run_key,
                stage="evaluate",
                job_id=job_id,
                error_message=failure_summary(error),
            )

    return {
        "evaluated_count": evaluated,
        "failed_job_ids": failed_job_ids,
        "quota_exhausted": bool(not_attempted_job_ids),
        "not_attempted_job_ids": not_attempted_job_ids,
        "needs_description_job_ids": needs_description_job_ids,
        "source_profile_id": source_profile_id,
        "source_profile_version": source_profile_version,
    }

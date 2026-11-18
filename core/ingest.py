from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from adapters.jobs.adzuna_api import AdzunaApiAdapter
from adapters.jobs.mock_adzuna import MockAdzunaAdapter
from adapters.jobs.mock_jooble import MockJoobleAdapter
from core.config import load_job_search_config
from core.db.connection import release_write_lock
from core.errors import UserFacingError, failure_summary
from core.job_filters import FILTER_KEYS, filter_reason, has_filters
from core.repositories.jobs import insert_job_if_new, job_already_saved
from core.repositories.runs import log_failed_job
from core.schemas import JobRecord, JobSearchConfig, Settings
from core.seniority import title_allowed

logger = logging.getLogger(__name__)


def _description_hash(job: JobRecord) -> str:
    payload = f"{job.title}|{job.company}|{job.description}".encode()
    return hashlib.sha256(payload).hexdigest()


def _adapter_for(
    source_name: str,
    settings: Settings,
    quota_subject: str | None = None,
    search_config: JobSearchConfig | None = None,
):
    root = Path(__file__).resolve().parents[1]
    if source_name == "adzuna_api":
        return AdzunaApiAdapter(
            db_path=settings.app.db_path,
            daily_limit=settings.api_limits.adzuna_daily_limit,
            global_daily_limit=settings.api_limits.adzuna_global_daily_limit,
            quota_subject=quota_subject,
            search_config=search_config,
        )
    if source_name == "mock_adzuna":
        return MockAdzunaAdapter(str(root / settings.mock_data.adzuna_file))
    if source_name == "mock_jooble":
        return MockJoobleAdapter(str(root / settings.mock_data.jooble_file))
    raise ValueError(f"Unsupported source adapter: {source_name}")


def run_ingest(
    conn,
    settings: Settings,
    run_key: str,
    quota_subject: str | None = None,
    owner_user_id: int | None = None,
    search_config: JobSearchConfig | None = None,
    fetch_limit: int | None = None,
) -> dict:
    """Fetch jobs from primary and secondary source, insert only unseen records.

    `fetch_limit` (never above the configured per-run cap) counts jobs that are actually new: postings the user
    already has are skipped before they count, so a small limit cannot be used up by duplicates.
    """
    cap = settings.pipeline.daily_limit
    limit = min(cap, fetch_limit) if fetch_limit is not None else cap
    inserted_ids: list[int] = []
    source_stats: list[dict] = []
    config = search_config or load_job_search_config()
    levels = config.target_levels
    filtering = has_filters(config)
    skipped_by_level = 0
    skipped_by_filters = dict.fromkeys(FILTER_KEYS, 0)
    duplicates_skipped = 0

    def accept(job: JobRecord) -> bool:
        nonlocal skipped_by_level, duplicates_skipped
        if not title_allowed(job.title, levels):
            skipped_by_level += 1
            return False
        reason = filter_reason(job, config) if filtering else None
        if reason is not None:
            skipped_by_filters[reason] += 1
            return False
        if owner_user_id is not None and job_already_saved(conn, job, _description_hash(job), owner_user_id):
            duplicates_skipped += 1
            return False
        return True

    for source in [settings.data_sources.primary, settings.data_sources.secondary]:
        if not source or source.lower() in {"none", "null", "disabled"}:
            continue

        try:
            adapter = _adapter_for(
                source,
                settings,
                quota_subject=quota_subject,
                search_config=search_config,
            )
            release_write_lock(conn)  # job-board call may take minutes
            jobs = adapter.fetch_jobs(
                limit=max(0, limit - len(inserted_ids)),
                accept=accept if levels or filtering or owner_user_id is not None else None,
            )
        except Exception as error:
            if not isinstance(error, UserFacingError):
                logger.exception("Job source %s failed (run_key=%s)", source, run_key)
            summary = failure_summary(error)
            log_failed_job(
                conn, run_key=run_key, stage="ingest", job_id=None, error_message=f"source={source}: {summary}"
            )
            source_stats.append({"source": source, "status": "failed", "error": summary})
            continue

        source_inserted = 0

        for job in jobs:
            if len(inserted_ids) >= limit:
                break
            inserted_id = insert_job_if_new(
                conn,
                job,
                description_hash=_description_hash(job),
                raw_payload=json.dumps(job.model_dump(by_alias=True), ensure_ascii=False),
                owner_user_id=owner_user_id,
            )
            if inserted_id is not None:
                inserted_ids.append(inserted_id)
                source_inserted += 1

        source_stats.append({"source": source, "status": "success", "fetched": len(jobs), "inserted": source_inserted})

        if len(inserted_ids) >= limit:
            break

    return {
        "inserted_count": len(inserted_ids),
        "inserted_job_ids": inserted_ids,
        "source_stats": source_stats,
        "skipped_by_level": skipped_by_level,
        "skipped_by_filters": skipped_by_filters,
        "duplicates_skipped": duplicates_skipped,
        "fetch_limit": limit,
    }

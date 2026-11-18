"""Request-independent task handlers shared by the local execution runtime."""

from __future__ import annotations

import hashlib
import json

from core.config import load_resume, load_settings
from core.db import db_conn
from core.errors import UserFacingError
from core.evaluate import run_evaluation
from core.generation_service import _run_cover_letter_generation, _run_resume_generation
from core.ingest import _description_hash, run_ingest
from core.prefilter import rank_by_relevance
from core.profile_readiness import assess_latest_profile_readiness
from core.re_evaluation_service import run_re_evaluation as _run_re_evaluation
from core.repositories.jobs import insert_job_if_new
from core.repositories.profiles import get_latest_candidate_profile
from core.repositories.runs import log_run
from core.request_normalization import parse_optional_bool as _to_optional_bool
from core.schemas import JobRecord
from core.search_preferences import get_effective_search_config
from core.time_utils import new_run_key, utc_today_iso
from core.user_scope import profile_scope_user_id as _profile_scope_user_id
from core.user_scope import quota_subject_for_user as _quota_subject_for_user
from core.users import get_user_by_id


def _run_resume_task_handler(
    task_id: str, payload: dict, owner_user_id: int, correlation_id: str, report_progress
) -> dict:
    settings = load_settings()
    try:
        job_id = int(payload.get("job_id"))
    except (TypeError, ValueError) as exc:
        raise UserFacingError("invalid payload: job_id must be integer") from exc

    profile_id_raw = payload.get("profile_id")
    style = str(payload.get("style", "ats")).strip() or "ats"
    decided_by = str(payload.get("decided_by", "task-runner")).strip() or "task-runner"

    report_progress("validating", 20, "validating resume task payload")
    with db_conn(settings.app.db_path) as conn:
        user_row = get_user_by_id(conn, int(owner_user_id))
        if user_row is None or not int(user_row["is_active"]):
            raise UserFacingError("task owner not found")
        report_progress("generating", 65, "generating targeted resume")
        result = _run_resume_generation(
            conn,
            settings,
            job_id=job_id,
            profile_id_raw=profile_id_raw,
            style=style,
            decided_by=decided_by,
            current_user=user_row,
        )
    report_progress("persisted", 95, "resume persisted")

    output = dict(result)
    output["task_id"] = task_id
    output["task_type"] = "generate_resume"
    output["result_ref"] = f"generated_resumes:{job_id}"
    output["correlation_id"] = correlation_id
    return output


def _run_cover_letter_task_handler(
    task_id: str,
    payload: dict,
    owner_user_id: int,
    correlation_id: str,
    report_progress,
) -> dict:
    settings = load_settings()
    try:
        job_id = int(payload.get("job_id"))
    except (TypeError, ValueError) as exc:
        raise UserFacingError("invalid payload: job_id must be integer") from exc

    profile_id_raw = payload.get("profile_id")
    tone = str(payload.get("tone", "formal")).strip() or "formal"

    report_progress("validating", 20, "validating cover-letter task payload")
    with db_conn(settings.app.db_path) as conn:
        user_row = get_user_by_id(conn, int(owner_user_id))
        if user_row is None or not int(user_row["is_active"]):
            raise UserFacingError("task owner not found")
        report_progress("generating", 65, "generating cover letter")
        result = _run_cover_letter_generation(
            conn,
            settings,
            job_id=job_id,
            profile_id_raw=profile_id_raw,
            tone=tone,
            current_user=user_row,
        )
    report_progress("persisted", 95, "cover letter persisted")

    output = dict(result)
    output["task_id"] = task_id
    output["task_type"] = "generate_cover_letter"
    output["result_ref"] = f"cover_letters:{job_id}"
    output["correlation_id"] = correlation_id
    return output


def _run_re_evaluate_task_handler(
    task_id: str,
    payload: dict,
    owner_user_id: int,
    correlation_id: str,
    report_progress,
) -> dict:
    settings = load_settings()
    scope = str(payload.get("scope", "all")).strip().lower() or "all"
    if scope not in {"all", "recent_days", "low_confidence", "high_risk", "unscored"}:
        raise UserFacingError("invalid payload: scope must be all|recent_days|low_confidence|high_risk|unscored")

    try:
        days = int(payload.get("days", 30))
        limit = int(payload.get("limit", 100))
    except (TypeError, ValueError) as exc:
        raise UserFacingError("invalid payload: days and limit must be integers") from exc

    raw_job_ids = payload.get("job_ids", [])
    explicit_job_ids: list[int] = []
    if isinstance(raw_job_ids, list):
        for item in raw_job_ids:
            try:
                explicit_job_ids.append(int(item))
            except (TypeError, ValueError):
                continue

    decided_by = str(payload.get("decided_by", "task-runner")).strip() or "task-runner"
    force_when_high_missing = bool(_to_optional_bool(payload.get("force_when_high_missing")))

    report_progress("validating", 20, "validating re-evaluation task payload")
    with db_conn(settings.app.db_path) as conn:
        user_row = get_user_by_id(conn, int(owner_user_id))
        if user_row is None or not int(user_row["is_active"]):
            raise UserFacingError("task owner not found")

        report_progress("evaluating", 65, "running re-evaluation")
        result = _run_re_evaluation(
            conn,
            settings=settings,
            scope=scope,
            days=days,
            limit=limit,
            explicit_job_ids=explicit_job_ids,
            decided_by=decided_by,
            quota_subject=_quota_subject_for_user(user_row),
            current_user=user_row,
            force_when_high_missing=force_when_high_missing,
        )

    if not result.get("ok"):
        message = str(result.get("error") or "re-evaluation failed").strip() or "re-evaluation failed"
        raise UserFacingError(message[:300])

    report_progress("persisted", 95, "re-evaluation persisted")
    summary = result["summary"]
    output = {
        "task_id": task_id,
        "task_type": "re_evaluate",
        "run_key": result["run_key"],
        "scope": result["scope"],
        "target_job_count": len(result["target_job_ids"]),
        "evaluated_count": int(summary["evaluated_count"]),
        "failed_job_ids": summary["failed_job_ids"],
        "quota_exhausted": bool(summary.get("quota_exhausted")),
        "not_attempted_count": len(summary.get("not_attempted_job_ids", [])),
        "needs_description_count": len(summary.get("needs_description_job_ids", [])),
        "source_profile_id": summary["source_profile_id"],
        "source_profile_version": summary["source_profile_version"],
        "readiness": result["readiness"],
        "readiness_override_applied": bool(result.get("readiness_override_applied")),
        "result_ref": f"runs:{result['run_key']}",
        "correlation_id": correlation_id,
    }
    return output


def _run_manual_search_task_handler(
    task_id: str,
    payload: dict,
    owner_user_id: int,
    correlation_id: str,
    report_progress,
) -> dict:
    settings = load_settings()
    force_when_high_missing = bool(_to_optional_bool(payload.get("force_when_high_missing")))

    report_progress("validating", 15, "validating manual-search task payload")
    with db_conn(settings.app.db_path) as conn:
        user_row = get_user_by_id(conn, int(owner_user_id))
        if user_row is None or not int(user_row["is_active"]):
            raise UserFacingError("task owner not found")

        profile_user_id = _profile_scope_user_id(user_row)
        quota_subject = _quota_subject_for_user(user_row)
        readiness = assess_latest_profile_readiness(conn, user_id=profile_user_id)
        high_missing_count = int(readiness.get("high_priority_missing_count") or 0)
        readiness_override_applied = bool(
            force_when_high_missing
            and high_missing_count > 0
            and readiness.get("review_status") == "approved"
            and not readiness["allowed"]
        )

        if not readiness["allowed"] and not readiness_override_applied:
            message = "; ".join(readiness.get("blocking_reasons") or []) or "profile is not ready"
            raise UserFacingError(message[:300])

        run_key = new_run_key("manual-search")
        log_run(
            conn,
            run_key,
            "manual_search",
            "started",
            f"manual search started,forced={int(readiness_override_applied)}",
        )

        conn.commit()
        report_progress("ingesting", 40, "running job ingestion")
        ingest_summary = run_ingest(
            conn,
            settings,
            run_key=run_key,
            quota_subject=quota_subject,
            owner_user_id=int(user_row["id"]),
            search_config=get_effective_search_config(conn, int(user_row["id"]))[0],
            fetch_limit=payload.get("fetch_limit"),
        )

        profile_row = get_latest_candidate_profile(conn, user_id=profile_user_id)
        # Release pending writes from ingest/log steps before evaluation may touch
        # quota accounting via another SQLite connection.
        conn.commit()
        inserted_ids = rank_by_relevance(conn, list(ingest_summary["inserted_job_ids"]), profile_row)
        conn.commit()
        score_limit = payload.get("score_limit")
        to_score = inserted_ids if score_limit is None else inserted_ids[: int(score_limit)]
        if to_score:
            report_progress("evaluating", 70, "running evaluation")
            eval_summary = run_evaluation(
                conn,
                settings=settings,
                resume=load_resume(),
                target_job_ids=to_score,
                run_key=run_key,
                profile_row=profile_row,
                force_profile_usage=True,
                quota_subject=quota_subject,
                profile_user_id=profile_user_id,
                on_progress=lambda done, total: report_progress(
                    "evaluating", 70 + int(24 * done / max(total, 1)), f"scored {done} of {total}"
                ),
            )
        else:
            eval_summary = {
                "evaluated_count": 0,
                "failed_job_ids": [],
                "quota_exhausted": False,
                "not_attempted_job_ids": [],
                "needs_description_job_ids": [],
            }
        not_scored_by_choice = len(inserted_ids) - len(to_score)

        failed_sources = [
            item
            for item in ingest_summary.get("source_stats", [])
            if isinstance(item, dict) and str(item.get("status", "")).lower() == "failed"
        ]
        if failed_sources and ingest_summary["inserted_count"] == 0 and eval_summary["evaluated_count"] == 0:
            first_failed = failed_sources[0]
            source_name = str(first_failed.get("source", "unknown_source"))
            source_error = str(first_failed.get("error", "ingest failed"))
            raise UserFacingError(f"{source_name}: {source_error}"[:300])

        if eval_summary["failed_job_ids"] or eval_summary["quota_exhausted"]:
            log_run(
                conn,
                run_key,
                "manual_search",
                "warning",
                f"inserted={ingest_summary['inserted_count']},evaluated={eval_summary['evaluated_count']},failed={len(eval_summary['failed_job_ids'])},quota_exhausted={int(eval_summary['quota_exhausted'])}",
            )
        else:
            log_run(
                conn,
                run_key,
                "manual_search",
                "success",
                f"inserted={ingest_summary['inserted_count']},evaluated={eval_summary['evaluated_count']}",
            )

    report_progress("persisted", 95, "manual-search persisted")
    output = {
        "task_id": task_id,
        "task_type": "manual_search",
        "run_key": run_key,
        "inserted_count": int(ingest_summary["inserted_count"]),
        "skipped_by_level": int(ingest_summary.get("skipped_by_level", 0)),
        "skipped_by_filters": dict(ingest_summary.get("skipped_by_filters", {})),
        "evaluated_count": int(eval_summary["evaluated_count"]),
        "failed_job_ids": list(eval_summary["failed_job_ids"]),
        "duplicates_skipped": int(ingest_summary.get("duplicates_skipped", 0)),
        "fetch_limit": int(ingest_summary.get("fetch_limit", 0)),
        "score_limit": payload.get("score_limit"),
        "quota_exhausted": bool(eval_summary["quota_exhausted"]),
        "not_scored_by_choice": not_scored_by_choice,
        "not_scored_by_quota": len(eval_summary["not_attempted_job_ids"]),
        "not_scored_no_description": len(eval_summary["needs_description_job_ids"]),
        "not_scored_count": not_scored_by_choice
        + len(eval_summary["not_attempted_job_ids"])
        + len(eval_summary["failed_job_ids"])
        + len(eval_summary["needs_description_job_ids"]),
        "source_stats": list(ingest_summary.get("source_stats", [])),
        "readiness": readiness,
        "readiness_override_applied": readiness_override_applied,
        "result_ref": f"runs:{run_key}",
        "correlation_id": correlation_id,
    }
    return output


def _run_manual_jd_match_task_handler(
    task_id: str,
    payload: dict,
    owner_user_id: int,
    correlation_id: str,
    report_progress,
) -> dict:
    settings = load_settings()
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    company = str(payload.get("company", "")).strip() or "Unknown Company"
    location = str(payload.get("location", "")).strip() or "unknown"
    source_url = str(payload.get("url", "")).strip() or "manual://pasted-jd"

    if not title or not description:
        raise UserFacingError("title and description are required")

    max_len = int(settings.pipeline.max_description_length)
    if len(description) > max_len:
        description = description[:max_len]

    def _to_optional_int(raw):
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        return int(text)

    try:
        salary_min = _to_optional_int(payload.get("salary_min"))
        salary_max = _to_optional_int(payload.get("salary_max"))
    except ValueError as exc:
        raise UserFacingError("invalid salary fields") from exc

    posted_date = utc_today_iso()
    external_id = hashlib.sha256(f"{title}|{company}|{location}|{description}".encode()).hexdigest()[:24]
    manual_job = JobRecord.model_validate(
        {
            "id": external_id,
            "title": title,
            "company": company,
            "location": location,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "description": description,
            "posted_date": posted_date,
            "source": "manual_jd_ui",
            "url": source_url,
        }
    )

    run_key = new_run_key("manual-jd")
    report_progress("validating", 15, "validating manual JD payload")

    with db_conn(settings.app.db_path) as conn:
        user_row = get_user_by_id(conn, int(owner_user_id))
        if user_row is None or not int(user_row["is_active"]):
            raise UserFacingError("task owner not found")

        profile_user_id = _profile_scope_user_id(user_row)
        if settings.llm.provider != "mock_gemini":
            readiness = assess_latest_profile_readiness(conn, user_id=profile_user_id)
            # A single pasted job only needs an approved profile with the essentials, not a complete one.
            if not readiness["minimum_ready"]:
                reasons = "; ".join(readiness["minimum_blocking_reasons"])
                raise UserFacingError(
                    f"approved master profile with name, skills and experience is required: {reasons}"
                )
        quota_subject = _quota_subject_for_user(user_row)
        log_run(conn, run_key, "manual_jd", "started", "manual jd match started")
        inserted_id = insert_job_if_new(
            conn,
            manual_job,
            description_hash=_description_hash(manual_job),
            raw_payload=json.dumps(
                {
                    "kind": "manual_jd_ui",
                    "title": title,
                    "company": company,
                    "location": location,
                    "description": description,
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "url": source_url,
                },
                ensure_ascii=False,
            ),
            owner_user_id=int(user_row["id"]),
        )

        if inserted_id is None:
            existing = conn.execute(
                """
                SELECT id
                FROM jobs
                WHERE source = ?
                  AND source_job_id = ?
                  AND owner_user_id = ?
                LIMIT 1
                """,
                ("manual_jd_ui", external_id, int(user_row["id"])),
            ).fetchone()
            if existing is None:
                raise UserFacingError("failed to persist manual jd")
            job_id = int(existing["id"])
        else:
            job_id = int(inserted_id)

        # Release pending writes before evaluation may use a secondary
        # SQLite connection for quota accounting.
        conn.commit()
        report_progress("evaluating", 65, "running manual JD evaluation")
        eval_summary = run_evaluation(
            conn,
            settings,
            load_resume(),
            [job_id],
            run_key=run_key,
            quota_subject=quota_subject,
            profile_user_id=profile_user_id,
        )

        if eval_summary["failed_job_ids"]:
            log_run(conn, run_key, "manual_jd", "warning", f"evaluation failed for job_id={job_id}")
            error_row = conn.execute(
                """
                SELECT error_message
                FROM failed_jobs
                WHERE run_key = ?
                  AND stage = 'evaluate'
                  AND job_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (run_key, job_id),
            ).fetchone()
            error_detail = (
                str(error_row["error_message"]).strip()
                if error_row is not None and error_row["error_message"] is not None
                else "llm evaluation failed"
            )
            raise UserFacingError(error_detail[:300])

        eval_row = conn.execute(
            "SELECT match_score FROM evaluations WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        match_score = int(eval_row["match_score"]) if eval_row is not None else None
        log_run(
            conn,
            run_key,
            "manual_jd",
            "success",
            f"manual jd matched job_id={job_id}, score={match_score if match_score is not None else ''}",
        )

    report_progress("persisted", 95, "manual JD match persisted")
    return {
        "task_id": task_id,
        "task_type": "manual_jd_match",
        "run_key": run_key,
        "job_id": int(job_id),
        "match_score": match_score,
        "correlation_id": correlation_id,
        "result_ref": f"evaluations:{job_id}",
    }

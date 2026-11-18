from __future__ import annotations

from core.config import load_resume
from core.evaluate import run_evaluation
from core.persistence import job_visibility_clause
from core.profile_readiness import assess_latest_profile_readiness
from core.repositories.profiles import get_latest_candidate_profile
from core.repositories.runs import log_run
from core.time_utils import new_run_key
from core.user_scope import profile_scope_user_id


def collect_re_evaluate_job_ids(
    conn,
    scope: str,
    days: int,
    limit: int,
    explicit_job_ids: list[int],
    current_user,
) -> list[int]:
    safe_limit = max(1, min(limit, 500))
    visibility_sql, visibility_args = job_visibility_clause(
        {**dict(current_user), "is_admin": 0} if current_user is not None else None, alias="j"
    )

    if explicit_job_ids:
        # Jobs the user names are scored whether or not they have a score yet (a first score is inserted).
        placeholders = ",".join(["?"] * len(explicit_job_ids))
        rows = conn.execute(
            f"""
            SELECT j.id AS job_id
            FROM jobs j
            WHERE j.id IN ({placeholders})
              AND {visibility_sql}
            ORDER BY j.id DESC
            LIMIT ?
            """,
            tuple(explicit_job_ids) + visibility_args + (safe_limit,),
        ).fetchall()
        return [int(row["job_id"]) for row in rows]

    if scope == "unscored":
        rows = conn.execute(
            f"""
            SELECT j.id AS job_id
            FROM jobs j
            LEFT JOIN evaluations e ON e.job_id = j.id
            WHERE e.job_id IS NULL
              AND j.archived_at IS NULL
              AND {visibility_sql}
            ORDER BY j.relevance IS NULL, j.relevance DESC, j.id DESC
            LIMIT ?
            """,
            visibility_args + (safe_limit,),
        ).fetchall()
        return [int(row["job_id"]) for row in rows]

    if scope == "recent_days":
        safe_days = max(1, min(days, 365))
        rows = conn.execute(
            f"""
            SELECT e.job_id
            FROM evaluations e
            JOIN jobs j ON j.id = e.job_id
            WHERE datetime(j.created_at) >= datetime('now', ?)
              AND {visibility_sql}
            ORDER BY e.job_id DESC
            LIMIT ?
            """,
            (f"-{safe_days} day",) + visibility_args + (safe_limit,),
        ).fetchall()
    elif scope == "low_confidence":
        rows = conn.execute(
            f"""
            SELECT e.job_id
            FROM evaluations e
            JOIN jobs j ON j.id = e.job_id
            WHERE lower(e.confidence_level) = 'low'
              AND {visibility_sql}
            ORDER BY e.job_id DESC
            LIMIT ?
            """,
            visibility_args + (safe_limit,),
        ).fetchall()
    elif scope == "high_risk":
        rows = conn.execute(
            f"""
            SELECT e.job_id
            FROM evaluations e
            JOIN jobs j ON j.id = e.job_id
            WHERE e.risk_flags IS NOT NULL
              AND trim(e.risk_flags) != '[]'
              AND {visibility_sql}
            ORDER BY e.job_id DESC
            LIMIT ?
            """,
            visibility_args + (safe_limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT e.job_id
            FROM evaluations e
            JOIN jobs j ON j.id = e.job_id
            WHERE {visibility_sql}
            ORDER BY e.job_id DESC
            LIMIT ?
            """,
            visibility_args + (safe_limit,),
        ).fetchall()

    return [int(row["job_id"]) for row in rows]


def run_re_evaluation(
    conn,
    settings,
    scope: str,
    days: int,
    limit: int,
    explicit_job_ids: list[int],
    decided_by: str,
    quota_subject: str | None,
    current_user,
    force_when_high_missing: bool = False,
) -> dict:
    scoped_user_id = profile_scope_user_id(current_user)
    readiness = assess_latest_profile_readiness(conn, user_id=scoped_user_id)
    high_missing_count = int(readiness.get("high_priority_missing_count") or 0)
    readiness_override_applied = bool(
        force_when_high_missing
        and high_missing_count > 0
        and readiness.get("review_status") == "approved"
        and not readiness["allowed"]
    )

    if not readiness["allowed"] and not readiness_override_applied:
        return {
            "ok": False,
            "readiness": readiness,
            "error": "profile is not ready for re-evaluation",
            "status_code": 409,
        }

    target_job_ids = collect_re_evaluate_job_ids(
        conn,
        scope=scope,
        days=days,
        limit=limit,
        explicit_job_ids=explicit_job_ids,
        current_user=current_user,
    )

    run_key = new_run_key("re-eval")
    log_run(
        conn,
        run_key,
        "re_evaluate",
        "started",
        f"scope={scope},target_jobs={len(target_job_ids)},decided_by={decided_by},forced={int(readiness_override_applied)}",
    )

    if not target_job_ids:
        log_run(conn, run_key, "re_evaluate", "success", "no target jobs for re-evaluation")
        return {
            "ok": True,
            "run_key": run_key,
            "scope": scope,
            "target_job_ids": [],
            "summary": {
                "evaluated_count": 0,
                "failed_job_ids": [],
                "quota_exhausted": False,
                "not_attempted_job_ids": [],
                "source_profile_id": readiness.get("profile_id"),
                "source_profile_version": readiness.get("profile_version"),
            },
            "readiness": readiness,
            "readiness_override_applied": readiness_override_applied,
        }

    profile_row = get_latest_candidate_profile(conn, user_id=scoped_user_id)
    summary = run_evaluation(
        conn,
        settings=settings,
        resume=load_resume(),
        target_job_ids=target_job_ids,
        run_key=run_key,
        profile_row=profile_row,
        force_profile_usage=True,
        quota_subject=quota_subject,
        profile_user_id=scoped_user_id,
    )

    if summary["failed_job_ids"] or summary["quota_exhausted"]:
        log_run(
            conn,
            run_key,
            "re_evaluate",
            "warning",
            f"evaluated={summary['evaluated_count']},failed={len(summary['failed_job_ids'])},quota_exhausted={int(summary['quota_exhausted'])}",
        )
    else:
        log_run(
            conn,
            run_key,
            "re_evaluate",
            "success",
            f"evaluated={summary['evaluated_count']}",
        )

    return {
        "ok": True,
        "run_key": run_key,
        "scope": scope,
        "target_job_ids": target_job_ids,
        "summary": summary,
        "readiness": readiness,
        "readiness_override_applied": readiness_override_applied,
    }

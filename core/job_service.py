"""Read models and simple writes for a user's jobs (used by /api/v1 and the fit-package route)."""

from __future__ import annotations

import sqlite3
from typing import Any

from core.evaluation_profile import evaluation_is_current
from core.job_text import description_hash, is_description_snippet
from core.posting_years import years_asked
from core.repositories.decisions import get_generation_decision
from core.repositories.profiles import get_latest_candidate_profile
from core.request_normalization import parse_json_dict, parse_text_list
from core.time_utils import utc_now_iso

_SUMMARY_COLUMNS = """
    j.id, j.title, j.company, j.location, j.source, j.url, j.posted_date, j.created_at,
    j.salary_min, j.salary_max, j.archived_at, j.relevance, e.match_score, e.recommendation_level,
    e.confidence_level AS confidence, e.source_profile_id, e.source_profile_version,
    COALESCE(a.status, 'draft') AS application_status, COALESCE(a.status_note, '') AS application_note,
    t.action AS triage, t.generate AS triage_generate,
    EXISTS (SELECT 1 FROM generated_resumes r WHERE r.job_id = j.id) AS has_resume,
    EXISTS (SELECT 1 FROM cover_letters c WHERE c.job_id = j.id) AS has_cover_letter
"""
_SUMMARY_JOINS = """
    FROM jobs j
    LEFT JOIN evaluations e ON e.job_id = j.id
    LEFT JOIN applications a ON a.job_id = j.id
    LEFT JOIN job_triage t ON t.job_id = j.id AND t.user_id = j.owner_user_id
"""


def _years_fields(description: str | None) -> dict[str, int | None]:
    """The years of experience the posting text asks for, derived on read so a full text replacing a preview counts."""
    years = years_asked(description)
    return {
        "years_asked_min": years.minimum if years else None,
        "years_asked_max": years.maximum if years else None,
    }


def _summary(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    return {**item, **_years_fields(item.pop("description"))}


def match_report(eval_row: sqlite3.Row | None) -> dict[str, Any] | None:
    if eval_row is None:
        return None
    return {
        "total_score": int(eval_row["total_score"])
        if eval_row["total_score"] is not None
        else int(eval_row["match_score"]),
        "match_score": int(eval_row["match_score"]),
        "dimension_scores": parse_json_dict(eval_row["dimension_scores_json"]),
        "match_reasons": parse_text_list(eval_row["match_reasons"], limit=8),
        "strengths": parse_text_list(eval_row["strengths"], limit=8),
        "gaps": parse_text_list(eval_row["gaps"], limit=8),
        "risk_flags": parse_text_list(eval_row["risk_flags"], limit=8),
        "recommendation_level": str(eval_row["recommendation_level"] or "maybe"),
        "confidence": str(eval_row["confidence_level"] or "medium"),
        "missing_information": parse_text_list(eval_row["missing_information"], limit=10),
        "fit_reason": str(eval_row["fit_reason"] or ""),
        "should_apply": bool(eval_row["should_apply"]),
        "model_name": str(eval_row["model_name"] or ""),
        "created_at": str(eval_row["created_at"] or ""),
        "source_profile_id": int(eval_row["source_profile_id"]) if eval_row["source_profile_id"] is not None else None,
        "source_profile_version": (
            int(eval_row["source_profile_version"]) if eval_row["source_profile_version"] is not None else None
        ),
    }


def list_jobs(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    min_score: int | None = None,
    q: str | None = None,
    include_archived: bool = False,
    triage: str | None = None,
    scored: bool | None = None,
    sort: str = "newest",
) -> dict[str, Any]:
    where = ["j.owner_user_id = ?"]
    args: list[Any] = [user_id]
    if not include_archived:
        where.append("j.archived_at IS NULL")
    if status is not None:
        where.append("COALESCE(a.status, 'draft') = ?")
        args.append(status)
    if triage == "pending":
        where.append("t.job_id IS NULL")
    elif triage is not None:
        where.append("t.action = ?")
        args.append({"skipped": "skipped", "waitlisted": "waitlisted", "accepted": "accepted"}[triage])
    if scored is not None:
        where.append("e.job_id IS NOT NULL" if scored else "e.job_id IS NULL")
    if min_score is not None:
        where.append("e.match_score >= ?")
        args.append(min_score)
    if q:
        where.append("(j.title LIKE ? ESCAPE '\\' OR j.company LIKE ? ESCAPE '\\')")
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        args += [pattern, pattern]
    where_sql = " AND ".join(where)
    order = "e.match_score IS NULL, e.match_score DESC, j.relevance DESC, j.id DESC" if sort == "score" else "j.id DESC"
    total = conn.execute(f"SELECT COUNT(*) {_SUMMARY_JOINS} WHERE {where_sql}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT {_SUMMARY_COLUMNS}, j.description {_SUMMARY_JOINS} "
        f"WHERE {where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
        [*args, limit, offset],
    ).fetchall()
    return {"items": [_summary(row) for row in rows], "total": int(total), "limit": limit, "offset": offset}


def _latest_document(conn: sqlite3.Connection, table: str, job_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        f"""SELECT id, version, created_at, source_profile_id, origin,
                   (SELECT COUNT(*) FROM {table} WHERE job_id = ?) AS version_count
            FROM {table} WHERE job_id = ? ORDER BY version DESC LIMIT 1""",
        (job_id, job_id),
    ).fetchone()
    return dict(row) if row is not None else None


def get_job_detail(conn: sqlite3.Connection, user_id: int, job_id: int) -> dict[str, Any] | None:
    job = conn.execute(
        f"SELECT {_SUMMARY_COLUMNS}, j.description, a.updated_at AS application_updated_at, "
        f"a.follow_up_at AS follow_up_at "
        f"{_SUMMARY_JOINS} WHERE j.id = ? AND j.owner_user_id = ?",
        (job_id, user_id),
    ).fetchone()
    if job is None:
        return None
    eval_row = conn.execute("SELECT * FROM evaluations WHERE job_id = ?", (job_id,)).fetchone()
    decision = get_generation_decision(conn, job_id)
    latest_profile = get_latest_candidate_profile(conn, user_id=user_id)
    report = match_report(eval_row)
    return {
        **{key: job[key] for key in job.keys() if key not in {"application_updated_at"}},
        "match": report,
        "match_uses_latest_profile": (
            eval_row is not None
            and latest_profile is not None
            and evaluation_is_current(conn, eval_row, latest_profile)
        ),
        "decision": {
            "viewed_match_at": decision["viewed_match_at"],
            "generate_resume": bool(decision["decision_generate_resume"]),
            "generate_cover_letter": bool(decision["decision_generate_cover_letter"]),
        }
        if decision is not None
        else None,
        "documents": {
            "resume": _latest_document(conn, "generated_resumes", job_id),
            "cover_letter": _latest_document(conn, "cover_letters", job_id),
        },
        "description_is_snippet": is_description_snippet(job["source"], job["description"]),
        **_years_fields(job["description"]),
        "application_updated_at": job["application_updated_at"],
    }


def set_job_archived(conn: sqlite3.Connection, user_id: int, job_id: int, archived: bool) -> bool:
    cursor = conn.execute(
        "UPDATE jobs SET archived_at = ? WHERE id = ? AND owner_user_id = ?",
        (utc_now_iso() if archived else None, job_id, user_id),
    )
    return cursor.rowcount == 1


def set_job_description(conn: sqlite3.Connection, user_id: int, job_id: int, description: str) -> bool:
    """Replace a job's text with the full posting the user pasted; False when the job is not theirs."""
    row = conn.execute(
        "SELECT title, company FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, user_id)
    ).fetchone()
    if row is None:
        return False
    conn.execute(
        "UPDATE jobs SET description = ?, description_hash = ? WHERE id = ?",
        (description, description_hash(row["title"], row["company"], description), job_id),
    )
    return True

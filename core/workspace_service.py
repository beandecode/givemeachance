"""Presentation-independent reads for a replacement web/mobile client.

The versioned workspace is always personal, including for administrators.
No DOM IDs, HTML fragments, template contexts or local filesystem paths escape here.
"""

from core.api_limits import get_daily_api_usage_for_subject_with_conn
from core.async_tasks import serialize_async_task
from core.generate_resume import parse_master_profile_row
from core.profile_readiness import assess_latest_profile_readiness
from core.repositories.profiles import get_latest_candidate_profile


def profile_resource(row):
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "profile_version": int(row["profile_version"]),
        "model_name": row["model_name"],
        "created_at": row["created_at"],
        "review_status": row["review_status"],
        "review_note": row["review_note"] or "",
        "reviewed_at_utc": row["reviewed_at_utc"],
        "master_profile": parse_master_profile_row(row),
    }


def profile_snapshot(conn, user_id):
    return {
        "profile": profile_resource(get_latest_candidate_profile(conn, user_id=user_id)),
        "readiness": assess_latest_profile_readiness(conn, user_id=user_id),
    }


def overview(conn, settings, user_id):
    counts = conn.execute(
        """SELECT COUNT(*) AS jobs, COUNT(e.id) AS evaluated,
                  SUM(CASE WHEN a.status IN ('submitted','interview','offer','hired','rejected','withdrawn')
                      THEN 1 ELSE 0 END) AS applications
           FROM jobs j LEFT JOIN evaluations e ON e.job_id = j.id
           LEFT JOIN applications a ON a.job_id = j.id WHERE j.owner_user_id = ?""",
        (user_id,),
    ).fetchone()
    return {
        "counts": {key: int(counts[key] or 0) for key in counts.keys()},
        "readiness": assess_latest_profile_readiness(conn, user_id=user_id),
        "usage": get_daily_api_usage_for_subject_with_conn(
            conn,
            f"user:{user_id}",
            {
                "gemini": settings.api_limits.gemini_daily_limit,
                "adzuna": settings.api_limits.adzuna_daily_limit,
            },
        ),
    }


def list_tasks(conn, user_id, *, limit=20, offset=0, active=False):
    where = "owner_user_id = ?" + (" AND state IN ('queued', 'running')" if active else "")
    total = conn.execute(f"SELECT COUNT(*) FROM async_tasks WHERE {where}", (user_id,)).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM async_tasks WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?", (user_id, limit, offset)
    ).fetchall()
    return {"items": [serialize_async_task(row) for row in rows], "total": total, "limit": limit, "offset": offset}

"""Where a user is in the flow, computed from stored data (ADR-015).

Nothing here is stored except the "skip the guide" flag: every step is derived from the profile, search settings,
jobs, swipe decisions, documents and applications, so the guide cannot disagree with the data. Reason codes are
stable identifiers the web app maps to copy; the generation gates use the same codes.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any, Literal

from core.job_service import get_job_detail
from core.preferences_service import get_preferences
from core.profile_readiness import assess_latest_profile_readiness
from core.repositories.preferences import read_sections, write_sections
from core.search_preferences import get_effective_search_config
from core.time_utils import utc_today_iso

StepStatus = Literal["done", "current", "todo"]

GLOBAL_STEPS = ("profile", "search_prefs", "find_jobs", "pick", "write", "apply")
JOB_STEPS = ("score", "write", "review", "applied", "follow_up")
_SECTION = "journey"
_SUBMITTED = ("submitted", "interview", "offer", "hired", "rejected", "withdrawn")
_OPEN = ("submitted", "interview")  # applications still waiting for an answer


def _step(key: str, status: StepStatus, *, reason_code: str | None = None, cta_label: str = "", cta_route: str = ""):
    return {"key": key, "status": status, "reason_code": reason_code, "cta_label": cta_label, "cta_route": cta_route}


def _mark_current(steps: list[dict[str, Any]]) -> str | None:
    """The first step that is not done is the current one; later ones stay todo."""
    current: str | None = None
    for step in steps:
        if step["status"] == "done":
            continue
        if current is None:
            current = step["key"]
            step["status"] = "current"
        else:
            step["status"] = "todo"
    return current


def _skipped(conn: sqlite3.Connection, user_id: int) -> bool:
    raw = read_sections(conn, user_id).get(_SECTION)
    if raw is None:
        return False
    try:
        return bool(json.loads(raw).get("skipped"))
    except (ValueError, AttributeError):
        return False


def set_journey_skipped(conn: sqlite3.Connection, user_id: int, skipped: bool) -> None:
    write_sections(conn, user_id, {_SECTION: json.dumps({"skipped": skipped})})


def _count(conn: sqlite3.Connection, sql: str, *args: Any) -> int:
    return int(conn.execute(sql, args).fetchone()[0])


def _counts(conn: sqlite3.Connection, user_id: int, min_score: int) -> dict[str, int]:
    live = "j.owner_user_id = ? AND j.archived_at IS NULL"
    return {
        "jobs": _count(conn, f"SELECT COUNT(*) FROM jobs j WHERE {live}", user_id),
        "scored": _count(
            conn, f"SELECT COUNT(*) FROM jobs j JOIN evaluations e ON e.job_id = j.id WHERE {live}", user_id
        ),
        "deck": _count(
            conn,
            f"""SELECT COUNT(*) FROM jobs j JOIN evaluations e ON e.job_id = j.id
                LEFT JOIN job_triage t ON t.job_id = j.id AND t.user_id = j.owner_user_id
                WHERE {live} AND t.job_id IS NULL AND e.match_score >= ?""",
            user_id,
            min_score,
        ),
        "pending": _count(
            conn,
            f"""SELECT COUNT(*) FROM jobs j JOIN evaluations e ON e.job_id = j.id
                LEFT JOIN job_triage t ON t.job_id = j.id AND t.user_id = j.owner_user_id
                WHERE {live} AND t.job_id IS NULL""",
            user_id,
        ),
        "accepted": _count(
            conn,
            "SELECT COUNT(*) FROM job_triage t WHERE t.user_id = ? AND t.action = 'accepted'",
            user_id,
        ),
        "documents": _count(
            conn,
            """SELECT COUNT(*) FROM jobs j WHERE j.owner_user_id = ? AND (
                   EXISTS (SELECT 1 FROM generated_resumes r WHERE r.job_id = j.id)
                   OR EXISTS (SELECT 1 FROM cover_letters c WHERE c.job_id = j.id))""",
            user_id,
        ),
        "applied": _count(
            conn,
            f"""SELECT COUNT(*) FROM jobs j JOIN applications a ON a.job_id = j.id
                WHERE j.owner_user_id = ? AND a.status IN ({",".join("?" * len(_SUBMITTED))})""",
            user_id,
            *_SUBMITTED,
        ),
    }


def discover_state(counts: dict[str, int]) -> str:
    """Why the Discover deck is empty (or not), so the screen can offer the right next action."""
    if counts["deck"] > 0:
        return "has_cards"
    if counts["jobs"] == 0:
        return "no_jobs"
    if counts["scored"] == 0:
        return "none_scored"
    if counts["pending"] > 0:
        return "below_threshold"
    return "all_decided"


def _next_job_to_write(conn: sqlite3.Connection, user_id: int) -> int | None:
    row = conn.execute(
        """SELECT j.id FROM job_triage t JOIN jobs j ON j.id = t.job_id
           WHERE t.user_id = ? AND t.action = 'accepted' AND j.archived_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM generated_resumes r WHERE r.job_id = j.id)
           ORDER BY t.decided_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    return int(row[0]) if row is not None else None


def get_journey(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    readiness = assess_latest_profile_readiness(conn, user_id=user_id)
    _, search_source = get_effective_search_config(conn, user_id)
    counts = _counts(conn, user_id, get_preferences(conn, user_id).deck.min_score)

    if readiness["minimum_ready"]:
        profile = _step("profile", "done")
    else:
        code = "profile_missing" if readiness.get("profile_id") is None else "profile_incomplete"
        if readiness.get("review_status") not in (None, "approved") and code == "profile_incomplete":
            code = "profile_not_approved"
        profile = _step("profile", "todo", reason_code=code, cta_label="Set up your profile", cta_route="/onboarding")

    prefs = (
        _step("search_prefs", "done")
        if search_source == "user"
        else _step(
            "search_prefs",
            "todo",
            reason_code="search_not_configured",
            cta_label="Choose what to search for",
            cta_route="/onboarding",
        )
    )
    find = (
        _step("find_jobs", "done")
        if counts["jobs"] > 0
        else _step("find_jobs", "todo", reason_code="no_jobs", cta_label="Search for jobs", cta_route="/jobs")
    )
    if counts["jobs"] > 0 and counts["scored"] == 0:
        find = _step(
            "find_jobs", "todo", reason_code="none_scored", cta_label="Score your jobs", cta_route="/jobs?view=unscored"
        )
    pick = (
        _step("pick", "done")
        if counts["accepted"] > 0 or counts["documents"] > 0
        else _step("pick", "todo", reason_code="nothing_accepted", cta_label="Pick jobs", cta_route="/discover")
    )
    to_write = _next_job_to_write(conn, user_id)
    write = (
        _step("write", "done")
        if counts["documents"] > 0
        else _step(
            "write",
            "todo",
            reason_code="no_documents",
            cta_label="Write a résumé",
            cta_route=f"/jobs/{to_write}" if to_write else "/discover",
        )
    )
    apply = (
        _step("apply", "done")
        if counts["applied"] > 0
        else _step(
            "apply", "todo", reason_code="nothing_applied", cta_label="Mark a job as applied", cta_route="/applications"
        )
    )

    steps = [profile, prefs, find, pick, write, apply]
    current = _mark_current(steps)
    skipped = _skipped(conn, user_id)
    return {
        "completed": current is None,
        "skipped": skipped,
        "current": current,
        "steps": steps,
        "counts": counts,
        "discover": discover_state(counts),
    }


def _latest_warnings(conn: sqlite3.Connection, job_id: int) -> list[str]:
    warnings: list[str] = []
    for table in ("generated_resumes", "cover_letters"):
        row = conn.execute(
            f"SELECT evidence_map_json FROM {table} WHERE job_id = ? ORDER BY version DESC LIMIT 1", (job_id,)
        ).fetchone()
        if row is None:
            continue
        try:
            found = json.loads(str(row["evidence_map_json"] or "{}")).get("warnings") or []
        except ValueError:
            found = []
        warnings.extend(str(item) for item in found)
    return warnings


def get_job_journey(conn: sqlite3.Connection, user_id: int, job_id: int) -> dict[str, Any] | None:
    """Steps for one job: score, write, review, apply, follow up; None when the job is not the user's."""
    detail = get_job_detail(conn, user_id, job_id)
    if detail is None:
        return None
    return build_job_journey(conn, detail)


def build_job_journey(conn: sqlite3.Connection, detail: dict[str, Any]) -> dict[str, Any]:
    job_id = int(detail["id"])
    status = str(detail["application_status"])
    has_document = bool(detail["documents"]["resume"] or detail["documents"]["cover_letter"])
    scored = detail["match"] is not None
    current_match = scored and bool(detail["match_uses_latest_profile"])
    warnings = _latest_warnings(conn, job_id) if has_document else []
    follow_up_at = detail.get("follow_up_at")

    if current_match:
        score = _step("score", "done")
    elif scored:
        score = _step("score", "todo", reason_code="match_stale", cta_label="Re-score with your latest profile")
    else:
        score = _step("score", "todo", reason_code="not_scored", cta_label="Score this job")

    if has_document:
        write = _step("write", "done")
    elif not current_match:
        write = _step("write", "todo", reason_code="needs_current_match", cta_label="Write my résumé")
    else:
        write = _step("write", "todo", reason_code="no_documents", cta_label="Write my résumé")

    # Review never blocks the next step: warnings are advice (core/document_checks.py), shown as "attention".
    if not has_document:
        review = _step("review", "todo", reason_code="no_documents")
    elif warnings:
        review = _step("review", "todo", reason_code="document_warnings")
    else:
        review = _step("review", "done")

    applied = (
        _step("applied", "done")
        if status in _SUBMITTED
        else _step("applied", "todo", reason_code="not_applied", cta_label="Mark as applied")
    )

    overdue = bool(follow_up_at) and status in _OPEN and str(follow_up_at) < utc_today_iso()
    if status not in _SUBMITTED:
        follow = _step("follow_up", "todo", reason_code="not_applied")
    elif status not in _OPEN or follow_up_at:
        follow = _step("follow_up", "done")
    else:
        follow = _step("follow_up", "todo", reason_code="no_follow_up", cta_label="Set a follow-up date")

    steps = [score, write, review, applied, follow]
    current = None
    for step in steps:
        if step["status"] == "done" or step["key"] == "review":
            continue
        current = step["key"]
        break
    for step in steps:
        if step["key"] == current:
            step["status"] = "current"
    return {
        "current": current,
        "steps": steps,
        "warning_count": len(warnings),
        "follow_up_at": str(follow_up_at) if follow_up_at else None,
        "follow_up_overdue": overdue,
    }


def valid_follow_up(value: str | None) -> str | None:
    """A YYYY-MM-DD date or None; raises ValueError for anything else."""
    if value is None or value == "":
        return None
    return date.fromisoformat(value).isoformat()

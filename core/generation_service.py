"""Document generation orchestration with ownership and manual decision gates.

Flow: check gates → release the database writer lock → LLM call → BEGIN IMMEDIATE →
re-check gates (the match report or profile may have changed meanwhile) → persist.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.db.connection import begin_write, release_write_lock
from core.errors import UserFacingError
from core.evaluation_profile import evaluation_is_current
from core.generate_cl import generate_cover_letter_content, persist_cover_letter
from core.generate_resume import (
    generate_targeted_resume_content,
    parse_master_profile_row,
    persist_generated_resume,
)
from core.persistence import load_scoped_job as _load_scoped_job
from core.profile_synthesis import without_placeholders
from core.repositories.applications import mark_application_materials_ready
from core.repositories.decisions import get_generation_decision, upsert_generation_decision
from core.repositories.profiles import get_candidate_profile, get_latest_candidate_profile
from core.user_scope import quota_subject_for_user as _quota_subject_for_user


class _GenerationError(UserFacingError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = str(message)
        self.status_code = int(status_code)


class _ResumeGenerationError(_GenerationError):
    pass


class _CoverLetterGenerationError(_GenerationError):
    pass


@dataclass(frozen=True)
class _DocumentKind:
    label: str
    decision_column: str
    error: type[_GenerationError]


_RESUME = _DocumentKind("resume", "decision_generate_resume", _ResumeGenerationError)
_COVER_LETTER = _DocumentKind("cover letter", "decision_generate_cover_letter", _CoverLetterGenerationError)


def _check_gates(conn, settings, kind: _DocumentKind, *, job_id: int, profile_id_raw, current_user):
    """Return (job_row, eval_row, profile_row) or raise kind.error with an HTTP status."""
    job_row = _load_scoped_job(conn, job_id, current_user)
    eval_row = conn.execute("SELECT * FROM evaluations WHERE job_id = ?", (job_id,)).fetchone()
    if job_row is None or eval_row is None:
        raise kind.error("job or evaluation not found", 404)

    profile_user_id = int(job_row["owner_user_id"])

    decision = get_generation_decision(conn, job_id)
    if decision is None or not decision["viewed_match_at"]:
        raise kind.error("match must be viewed before generation", 409)
    if not bool(decision[kind.decision_column]):
        raise kind.error(f"{kind.label} generation not selected", 409)

    if profile_id_raw is not None:
        try:
            profile_row = get_candidate_profile(conn, int(profile_id_raw), user_id=profile_user_id)
        except (TypeError, ValueError) as exc:
            raise kind.error("invalid profile_id", 400) from exc
        if profile_row is None:
            raise kind.error("profile_id not found", 404)
    else:
        profile_row = get_latest_candidate_profile(conn, user_id=profile_user_id)

    if profile_row is not None and profile_row["review_status"] != "approved":
        raise kind.error("selected master profile must be approved before generation", 409)
    if profile_row is None and settings.llm.provider != "mock_gemini":
        raise kind.error("approved master profile is required before generation", 409)
    # Same profile, or an edit the scorer cannot see (a corrected name or phone number): the match still holds.
    if not evaluation_is_current(conn, eval_row, profile_row):
        raise kind.error("match report uses a different profile version; re-evaluate and review the match first", 409)
    return job_row, eval_row, profile_row


def _recheck_gates_for_write(conn, settings, kind: _DocumentKind, *, job_id, profile_id_raw, current_user, used):
    """Re-run the gates inside the write transaction; the inputs used for the LLM call must still hold."""
    begin_write(conn)
    _, eval_row, profile_row = _check_gates(
        conn, settings, kind, job_id=job_id, profile_id_raw=profile_id_raw, current_user=current_user
    )
    used_eval, used_profile = used
    current = (eval_row["created_at"], profile_row["id"] if profile_row is not None else None)
    before = (used_eval["created_at"], used_profile["id"] if used_profile is not None else None)
    if current != before:
        raise kind.error("the match report or profile changed during generation; review the match and retry", 409)


def _run_resume_generation(
    conn,
    settings,
    *,
    job_id: int,
    profile_id_raw,
    style: str,
    decided_by: str,
    current_user,
) -> dict:
    gate_args = {"job_id": job_id, "profile_id_raw": profile_id_raw, "current_user": current_user}
    job_row, eval_row, profile_row = _check_gates(conn, settings, _RESUME, **gate_args)

    release_write_lock(conn)
    content_md, evidence_map = generate_targeted_resume_content(
        settings=settings,
        job_row=job_row,
        eval_row=eval_row,
        master_profile=without_placeholders(parse_master_profile_row(profile_row)),
        style=style,
        quota_subject=_quota_subject_for_user(current_user),
    )

    _recheck_gates_for_write(conn, settings, _RESUME, **gate_args, used=(eval_row, profile_row))
    result = persist_generated_resume(
        conn,
        db_path=settings.app.db_path,
        job_id=job_id,
        content_md=content_md,
        source_profile_id=int(profile_row["id"]) if profile_row is not None else None,
        evidence_map=evidence_map,
    )
    upsert_generation_decision(
        conn,
        job_id=job_id,
        generate_resume=True,
        generate_cover_letter=None,
        decided_by=decided_by,
    )
    mark_application_materials_ready(conn, job_id, note="resume generated")
    return result


def _run_cover_letter_generation(
    conn,
    settings,
    *,
    job_id: int,
    profile_id_raw,
    tone: str,
    current_user,
) -> dict:
    gate_args = {"job_id": job_id, "profile_id_raw": profile_id_raw, "current_user": current_user}
    job_row, eval_row, profile_row = _check_gates(conn, settings, _COVER_LETTER, **gate_args)

    release_write_lock(conn)
    content_md, evidence_map = generate_cover_letter_content(
        settings=settings,
        job_row=job_row,
        eval_row=eval_row,
        master_profile=without_placeholders(parse_master_profile_row(profile_row)),
        tone=tone,
        quota_subject=_quota_subject_for_user(current_user),
    )

    _recheck_gates_for_write(conn, settings, _COVER_LETTER, **gate_args, used=(eval_row, profile_row))
    result = persist_cover_letter(
        conn,
        settings.app.db_path,
        job_id,
        content_md,
        source_profile_id=int(profile_row["id"]) if profile_row is not None else None,
        evidence_map=evidence_map,
    )
    mark_application_materials_ready(conn, job_id, note="cover letter generated")
    return result

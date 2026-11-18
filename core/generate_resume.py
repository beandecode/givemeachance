from __future__ import annotations

import json

from adapters.llm import get_llm
from core.document_generation import generate_checked_document
from core.profile_quality import with_computed_completeness
from core.repositories.documents import insert_generated_resume
from core.schemas import Settings


def generate_targeted_resume_content(
    settings: Settings,
    job_row,
    eval_row,
    master_profile: dict | None,
    style: str = "ats",
    quota_subject: str | None = None,
) -> tuple[str, dict]:
    """Generate targeted resume content strictly via LLM rewrite path."""
    document_model = settings.llm.document_model
    evaluator = get_llm(settings, quota_subject=quota_subject, model=document_model)
    profile = master_profile or {}

    def audit(content_md: str) -> dict:
        auditor = get_llm(settings, quota_subject=quota_subject, model=settings.llm.audit_model)
        return auditor.audit_document(profile, content_md, "resume")

    def rewrite(job: dict, match_report: dict, fixes: list[str] | None) -> dict:
        return evaluator.rewrite_resume(
            master_profile=profile, job=job, match_report=match_report, style=style, fixes=fixes
        )

    return generate_checked_document(
        "resume",
        "resume",
        rewrite,
        job_row,
        eval_row,
        master_profile,
        document_model or settings.llm.model,
        {"style": style, "prompt_version": settings.llm.prompt_version},
        audit=audit if settings.llm.audit_documents else None,
    )


def persist_generated_resume(
    conn,
    db_path: str,
    job_id: int,
    content_md: str,
    source_profile_id: int | None,
    evidence_map: dict | None = None,
) -> dict:
    row = insert_generated_resume(
        conn,
        job_id=job_id,
        content_md=content_md,
        source_profile_id=source_profile_id,
        evidence_map_json=json.dumps(evidence_map or {}, ensure_ascii=False),
    )

    return {
        "resume_id": int(row["id"]),
        "job_id": int(row["job_id"]),
        "version": int(row["version"]),
        "source_profile_id": int(row["source_profile_id"]) if row["source_profile_id"] is not None else None,
        "evidence_map": json.loads(str(row["evidence_map_json"] or "{}")),
    }


def parse_master_profile_row(row) -> dict | None:
    if row is None:
        return None
    text = row["master_profile_json"]
    if not text:
        return None
    try:
        profile = json.loads(text)
        return with_computed_completeness(profile) if isinstance(profile, dict) else None
    except json.JSONDecodeError:
        return None

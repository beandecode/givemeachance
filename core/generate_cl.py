from __future__ import annotations

import json

from adapters.llm import get_llm
from core.document_generation import generate_checked_document
from core.repositories.documents import insert_document_version
from core.schemas import Settings


def generate_cover_letter_content(
    settings: Settings,
    job_row,
    eval_row,
    master_profile: dict | None,
    tone: str = "formal",
    quota_subject: str | None = None,
) -> tuple[str, dict]:
    """Generate cover letter and evidence map strictly via LLM rewrite path."""
    document_model = settings.llm.document_model
    evaluator = get_llm(settings, quota_subject=quota_subject, model=document_model)
    profile = master_profile or {}

    def audit(content_md: str) -> dict:
        auditor = get_llm(settings, quota_subject=quota_subject, model=settings.llm.audit_model)
        return auditor.audit_document(profile, content_md, "cover_letter")

    def rewrite(job: dict, match_report: dict, fixes: list[str] | None) -> dict:
        return evaluator.rewrite_cover_letter(
            master_profile=profile, job=job, match_report=match_report, tone=tone, fixes=fixes
        )

    return generate_checked_document(
        "cover_letter",
        "cover letter",
        rewrite,
        job_row,
        eval_row,
        master_profile,
        document_model or settings.llm.model,
        {"tone": tone, "prompt_version": settings.llm.prompt_version},
        audit=audit if settings.llm.audit_documents else None,
    )


def persist_cover_letter(
    conn,
    db_path: str,
    job_id: int,
    content_md: str,
    source_profile_id: int | None = None,
    evidence_map: dict | None = None,
) -> dict:
    """Persist cover letter in database and export a markdown file."""
    row = insert_document_version(
        conn,
        "cover_letter",
        job_id=job_id,
        content_md=content_md,
        source_profile_id=source_profile_id,
        evidence_map_json=json.dumps(evidence_map or {}, ensure_ascii=False),
    )
    version = int(row["version"])

    return {
        "job_id": job_id,
        "version": version,
        "source_profile_id": source_profile_id,
        "evidence_map": evidence_map or {},
    }

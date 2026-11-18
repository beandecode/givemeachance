"""Shared core of résumé and cover-letter generation: rewrite, check, retry once, then fact-check."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.document_checks import check_generated_document
from core.errors import UserFacingError
from core.parsing import parse_list_field

Rewrite = Callable[[dict, dict, list[str] | None], dict]
Audit = Callable[[str], dict]  # document text -> {"claims": [...], "model_name": str}
MAX_AUDIT_FIXES = 8
MAX_AUDIT_WARNINGS = 5


def job_for_prompt(job_row) -> dict[str, Any]:
    return {
        "title": job_row["title"],
        "company": job_row["company"],
        "location": job_row["location"],
        "description": job_row["description"],
    }


def match_report_for_prompt(eval_row) -> dict[str, Any]:
    """The writer's brief: what makes the candidate strong for this job, and what not to claim.

    The writers are the candidate's advocates, so they get the strengths and the reasons for the fit, never the score,
    the recommendation, the confidence or the risk flags: a writer told that the fit is weak writes a timid document.
    The gaps are passed only so that the writer neither claims them nor mentions them.
    """
    return {
        "fit_reason": eval_row["fit_reason"],
        "strengths": parse_list_field(eval_row["strengths"]),
        "match_reasons": parse_list_field(eval_row["match_reasons"]),
        "requirements_not_met": parse_list_field(eval_row["gaps"]),
    }


def _content(rewritten: dict, label: str) -> str:
    content_md = str(rewritten.get("content_md", "")).strip()
    if not content_md:
        raise RuntimeError(f"LLM {label} rewrite returned empty content")
    return content_md


def _unsupported(audited: dict) -> list[dict]:
    return [claim for claim in audited.get("claims", []) if claim.get("status") == "unsupported"]


def generate_checked_document(
    kind: str,
    label: str,
    rewrite: Rewrite,
    job_row,
    eval_row,
    master_profile: dict | None,
    default_model: str,
    options: dict[str, str],
    audit: Audit | None = None,
) -> tuple[str, dict]:
    """Rewrite once, check the text, and rewrite again with the problems listed if any are serious.

    With `audit`, a second model links each claim to a profile fact; claims it calls unsupported earn one more targeted
    rewrite. `options` (style or tone) is copied into the evidence map. Problems that remain are kept as `warnings`
    for the user instead of blocking the document, and a failed audit never blocks it either.
    """
    job = job_for_prompt(job_row)
    report = match_report_for_prompt(eval_row)
    rewritten = rewrite(job, report, None)
    content = _content(rewritten, label)
    check = check_generated_document(kind, content, master_profile, job, report)
    retried = False
    if check.violations:
        retried = True
        second = rewrite(job, report, check.violations)
        second_content = _content(second, label)
        second_check = check_generated_document(kind, second_content, master_profile, job, report)
        if len(second_check.violations) <= len(check.violations):
            rewritten, content, check = second, second_content, second_check

    audited: dict | None = None
    audit_info: dict[str, Any] | None = None
    if audit is not None:
        try:
            audited = audit(content)
            audit_info = {"status": "ok", "model_name": str(audited.get("model_name", "")), "rewritten": False}
            unsupported = _unsupported(audited)
            if unsupported:
                fixes = [
                    "Restate this claim using only facts in the master_profile, keeping its strength; remove it only "
                    f"if no fact supports it: {claim['text']}"
                    for claim in unsupported[:MAX_AUDIT_FIXES]
                ]
                third = rewrite(job, report, fixes)
                third_content = _content(third, label)
                third_check = check_generated_document(kind, third_content, master_profile, job, report)
                third_audit = audit(third_content)
                # Keep the new draft only when it is strictly better: fewer unsupported claims, no new violations.
                if len(_unsupported(third_audit)) < len(unsupported) and len(third_check.violations) <= len(
                    check.violations
                ):
                    rewritten, content, check, audited = third, third_content, third_check, third_audit
                    audit_info["rewritten"] = True
        except UserFacingError as error:
            audited, audit_info = None, {"status": "skipped", "reason": str(error)[:160]}

    evidence_map: dict[str, Any] = {
        "mode": "llm",
        **options,
        "model_name": str(rewritten.get("model_name", default_model)),
        "evidence_notes": [str(x) for x in rewritten.get("evidence_notes", [])][:12],
    }
    if retried:
        evidence_map["retried"] = True
    warnings = [*check.violations, *check.warnings]
    if audit_info is not None:
        evidence_map["audit"] = audit_info
        if audited is not None:
            evidence_map["claims"] = audited.get("claims", [])[:40]
            remaining = _unsupported(audited)
            audit_info["unsupported"] = len(remaining)
            warnings.extend(
                f"Not supported by your profile: {claim['text']}" for claim in remaining[:MAX_AUDIT_WARNINGS]
            )
        else:
            warnings.append("The fact check could not run, so read every claim yourself before you send it")
    if warnings:
        evidence_map["warnings"] = warnings
    return content + "\n", evidence_map

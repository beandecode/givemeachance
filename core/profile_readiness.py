from __future__ import annotations

import json
from typing import Any

from core.parsing import is_core_high_field
from core.profile_quality import compute_profile_completeness
from core.repositories.profiles import get_latest_candidate_profile
from core.time_utils import utc_now_iso


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _to_missing_items(master_profile: dict | None) -> list[dict]:
    if not isinstance(master_profile, dict):
        return []
    raw = master_profile.get("missing_information")
    if not isinstance(raw, list):
        return []

    items: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        priority = _safe_text(item.get("priority")).lower() or "medium"
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        if priority == "high" and not is_core_high_field(item.get("field")):
            priority = "medium"

        items.append(
            {
                "field": _safe_text(item.get("field")) or "unknown_field",
                "question": _safe_text(item.get("question")) or "Please provide missing details.",
                "priority": priority,
            }
        )
    return items


def assess_profile_readiness(master_profile: dict | None, profile_meta: dict | None = None) -> dict:
    profile_meta = profile_meta or {}

    blocking_reasons: list[str] = []
    suggested_actions: list[str] = []

    if not isinstance(master_profile, dict):
        blocking_reasons.append("master profile not found")
        suggested_actions.append("Run profile synthesis before triggering search or re-evaluation.")
        return {
            "allowed": False,
            "minimum_ready": False,
            "minimum_blocking_reasons": list(blocking_reasons),
            "profile_id": profile_meta.get("id"),
            "profile_version": profile_meta.get("profile_version"),
            "completeness_score": 0,
            "high_priority_missing_count": 0,
            "blocking_reasons": blocking_reasons,
            "suggested_actions": suggested_actions,
            "checked_at": utc_now_iso(),
        }

    completeness_score = compute_profile_completeness(master_profile)
    missing_items = _to_missing_items(master_profile)
    high_missing = [item for item in missing_items if item.get("priority") == "high"]
    review_status = _safe_text(profile_meta.get("review_status")).lower()

    identity = master_profile.get("identity") if isinstance(master_profile.get("identity"), dict) else {}
    name = _safe_text(identity.get("name"))
    core_skills = master_profile.get("core_skills") if isinstance(master_profile.get("core_skills"), list) else []
    experiences = master_profile.get("experiences") if isinstance(master_profile.get("experiences"), list) else []

    # (reason, suggested action, minimum): "minimum" reasons also block pasting a single job description.
    checks: list[tuple[str, str, bool]] = []
    if completeness_score < 70:
        checks.append(
            (
                f"profile completeness too low ({completeness_score} < 70)",
                "Supplement profile details to increase completeness score to at least 70.",
                False,
            )
        )
    if high_missing:
        checks.append(
            (
                f"high priority missing information exists ({len(high_missing)} items)",
                "Answer high-priority missing fields on your profile page.",
                False,
            )
        )
    if not name or name.lower() == "unknown":
        checks.append(("candidate name is missing", "Provide candidate_name in profile synthesis or supplement.", True))
    if len(core_skills) < 3:
        checks.append(("core_skills is insufficient (< 3)", "Provide at least 3 core skills.", True))
    if not experiences:
        checks.append(("experiences is empty", "Provide at least one experience item.", True))
    if review_status and review_status != "approved":
        checks.append(
            (
                "latest master profile has not been approved",
                "Review and approve the latest Master Profile before search or generation.",
                True,
            )
        )
    blocking_reasons.extend(reason for reason, _, _ in checks)
    suggested_actions.extend(action for _, action, _ in checks)
    minimum_blocking_reasons = [reason for reason, _, minimum in checks if minimum]

    return {
        "allowed": len(blocking_reasons) == 0,
        "minimum_ready": len(minimum_blocking_reasons) == 0,
        "minimum_blocking_reasons": minimum_blocking_reasons,
        "profile_id": profile_meta.get("id"),
        "profile_version": profile_meta.get("profile_version"),
        "review_status": review_status or None,
        "completeness_score": completeness_score,
        "high_priority_missing_count": len(high_missing),
        "blocking_reasons": blocking_reasons,
        "suggested_actions": suggested_actions,
        "checked_at": utc_now_iso(),
    }


def assess_latest_profile_readiness(conn, user_id: int | None = None) -> dict:
    row = get_latest_candidate_profile(conn, user_id=user_id)
    if row is None:
        return assess_profile_readiness(master_profile=None, profile_meta=None)

    profile_meta = {
        "id": int(row["id"]),
        "profile_version": int(row["profile_version"]),
        "model_name": str(row["model_name"]),
        "created_at": str(row["created_at"]),
        "review_status": str(row["review_status"] or "pending"),
        "review_note": str(row["review_note"] or ""),
        "reviewed_at_utc": str(row["reviewed_at_utc"] or ""),
    }

    raw = str(row["master_profile_json"] or "")
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    result = assess_profile_readiness(payload, profile_meta=profile_meta)
    result["profile_meta"] = profile_meta
    return result

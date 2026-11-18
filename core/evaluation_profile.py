"""What the scorer sees of a candidate, and when an evaluation still describes the current profile.

The projection is the exact input of the evaluation prompt. Its fingerprint tells a typo fix in the name or the
contact details (not part of the projection) from a change that really affects matching (skills, experience, level).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from core.repositories.profiles import get_candidate_profile


def _collect_profile_skills(master_profile: dict) -> list[str]:
    raw_skills: list[str] = []

    raw_skills.extend([str(item) for item in master_profile.get("core_skills", [])])

    skill_matrix = master_profile.get("skill_matrix")
    if isinstance(skill_matrix, dict):
        for value in skill_matrix.values():
            if isinstance(value, list):
                raw_skills.extend([str(item) for item in value])

    for exp in master_profile.get("experiences", []):
        if isinstance(exp, dict):
            raw_skills.extend([str(item) for item in exp.get("tech_stack", [])])

    for proj in master_profile.get("projects", []):
        if isinstance(proj, dict):
            raw_skills.extend([str(item) for item in proj.get("tech_stack", [])])

    for cert in master_profile.get("certifications", []):
        if isinstance(cert, dict):
            raw_skills.append(str(cert.get("name", "")))
        else:
            raw_skills.append(str(cert))

    deduped: list[str] = []
    seen: set[str] = set()
    for item in raw_skills:
        text = str(item).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= 40:
            break

    return deduped


_UNKNOWN = {"", "unknown", "n/a", "none"}


def _known(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.casefold() in _UNKNOWN else text


def _known_list(value: object, limit: int) -> list[str]:
    items = value if isinstance(value, list) else []
    return [text for text in (_known(item) for item in items) if text][:limit]


def _as_text_list(value: object) -> list[str]:
    """Strings, or {"name": ...} records, as plain text."""
    items = value if isinstance(value, list) else []
    return [str(item.get("name", "")) if isinstance(item, dict) else str(item) for item in items]


def evaluation_projection(master_profile: dict) -> dict:
    """What the scorer sees of the candidate: level, skills, experience, projects, education, licences, spoken
    languages and preferences. Everything that can make the candidate stronger for a job belongs here.

    Name, email and phone are left out on purpose: they do not help matching and should not leave the app.
    The `skills.core` key is also what the mock evaluator reads.
    """
    raw_identity = master_profile.get("identity")
    identity: dict = raw_identity if isinstance(raw_identity, dict) else {}
    raw_preferences = master_profile.get("preferences")
    preferences: dict = raw_preferences if isinstance(raw_preferences, dict) else {}

    education_values = []
    for item in master_profile.get("education", []):
        if isinstance(item, dict):
            degree = str(item.get("degree", "")).strip()
            school = str(item.get("school", "")).strip()
            combined = " - ".join([part for part in [degree, school] if part])
            if combined:
                education_values.append(combined)
        else:
            text = str(item).strip()
            if text:
                education_values.append(text)

    experiences = [item for item in master_profile.get("experiences", []) if isinstance(item, dict)]
    projects = [item for item in master_profile.get("projects", []) if isinstance(item, dict)]
    candidate = {
        "current_title": _known(identity.get("current_title")),
        "years_experience": _known(identity.get("years_experience")),
        "location": _known(identity.get("location")),
        "summary": _known(master_profile.get("profile_summary")),
        "work_authorization": _known(preferences.get("work_authorization")),
        "target_roles": _known_list(preferences.get("target_roles"), 10),
        "preferred_locations": _known_list(preferences.get("preferred_locations"), 10),
        "highlights": _known_list(master_profile.get("career_highlights"), 5),
        "spoken_languages": _known_list(_as_text_list(master_profile.get("languages")), 8),
    }
    return {
        "candidate": {key: value for key, value in candidate.items() if value},
        "skills": {
            "core": _collect_profile_skills(master_profile),
        },
        "experience": [
            {
                "title": str(item.get("title", "Experience")),
                "company": str(item.get("company", "Unknown")),
                "duration": str(item.get("duration", "unknown")),
                "type": _known(item.get("employment_type")),
                "responsibilities": [
                    str(x)
                    for x in (list(item.get("highlights", []))[:6] + list(item.get("achievements", []))[:4])
                    if str(x).strip()
                ],
            }
            for item in experiences[:8]
        ],
        "projects": [
            {
                "name": str(item.get("name", "")),
                "summary": _known(item.get("summary")),
                "impact": _known_list(item.get("impact"), 2),
                "tech_stack": _known_list(item.get("tech_stack"), 8),
            }
            for item in projects[:3]
        ],
        "education": education_values,
        "certifications_and_licences": _known_list(_as_text_list(master_profile.get("certifications")), 10),
    }


def profile_fingerprint(master_profile: dict) -> str:
    """Stable hash of what the scorer sees; equal fingerprints mean an evaluation is still valid."""
    canonical = json.dumps(evaluation_projection(master_profile), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row_fingerprint(profile_row) -> str | None:
    try:
        master_profile = json.loads(str(profile_row["master_profile_json"] or "{}"))
    except json.JSONDecodeError:
        return None
    return profile_fingerprint(master_profile) if isinstance(master_profile, dict) else None


def evaluation_is_current(conn: sqlite3.Connection, eval_row, profile_row) -> bool:
    """True when the evaluation was made from `profile_row`, or from a version the scorer cannot tell apart from it."""
    evaluated_id = eval_row["source_profile_id"]
    if profile_row is None:
        return evaluated_id is None
    if evaluated_id is None:
        return False
    if int(evaluated_id) == int(profile_row["id"]):
        return True
    stored = eval_row["source_profile_fingerprint"]
    if not stored:  # evaluations from before fingerprints were stored: derive it from the version they used
        old_row = get_candidate_profile(conn, int(evaluated_id))
        stored = _row_fingerprint(old_row) if old_row is not None else None
    return bool(stored) and stored == _row_fingerprint(profile_row)

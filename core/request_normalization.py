from __future__ import annotations

import json


def parse_optional_bool(raw):
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return None


def parse_list_input(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        values: list[str] = []
        for item in raw:
            text = str(item).strip()
            if text:
                values.append(text)
        return values

    values: list[str] = []
    for chunk in str(raw).replace(",", "\n").splitlines():
        text = chunk.strip()
        if text:
            values.append(text)
    return values


def parse_text_list(raw, limit: int = 8) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                items = parsed
            else:
                items = [line.strip() for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError:
            items = [line.strip() for line in text.splitlines() if line.strip()]

    result: list[str] = []
    for item in items:
        line = str(item).strip()
        if not line:
            continue
        result.append(line)
        if len(result) >= limit:
            break
    return result


def parse_json_dict(raw) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return {}
    return {}


def normalize_user_details(raw: dict | None) -> dict:
    source = raw if isinstance(raw, dict) else {}
    supplement_overrides = source.get("supplement_overrides")
    return {
        "candidate_name": str(source.get("candidate_name", "")).strip(),
        "current_title": str(source.get("current_title", "")).strip(),
        "location": str(source.get("location", "")).strip(),
        "years_experience": str(source.get("years_experience", "")).strip(),
        "email": str(source.get("email", "")).strip(),
        "phone": str(source.get("phone", "")).strip(),
        "work_authorization": str(source.get("work_authorization", "")).strip(),
        "target_roles": parse_list_input(source.get("target_roles", [])),
        "preferred_locations": parse_list_input(source.get("preferred_locations", [])),
        "key_skills": str(source.get("key_skills", "")).strip(),
        "links": parse_list_input(source.get("links", [])),
        "education_items": parse_list_input(source.get("education_items", [])),
        "certifications": parse_list_input(source.get("certifications", [])),
        "languages": parse_list_input(source.get("languages", [])),
        "experience_notes": str(source.get("experience_notes", "")).strip(),
        "experience_date_hint": str(source.get("experience_date_hint", "")).strip(),
        "supplement_overrides": supplement_overrides if isinstance(supplement_overrides, dict) else {},
    }


def apply_supplement_answer(user_details: dict, field: str, answer: str) -> None:
    text = answer.strip()
    if not text:
        return

    if field == "identity.name":
        user_details["candidate_name"] = text
    elif field == "identity.current_title":
        user_details["current_title"] = text
    elif field == "identity.location":
        user_details["location"] = text
    elif field == "identity.years_experience":
        user_details["years_experience"] = text
    elif field == "identity.contact.email":
        user_details["email"] = text
    elif field == "identity.contact.phone":
        user_details["phone"] = text
    elif field == "preferences.work_authorization":
        user_details["work_authorization"] = text
    elif field == "preferences.target_roles":
        user_details["target_roles"] = parse_list_input(text)
    elif field == "preferences.preferred_locations":
        user_details["preferred_locations"] = parse_list_input(text)
    elif field == "core_skills":
        user_details["key_skills"] = text
    elif field in {"identity.contact.links", "links"}:
        user_details["links"] = parse_list_input(text)
    elif field == "education":
        user_details["education_items"] = parse_list_input(text)
    elif field == "certifications":
        user_details["certifications"] = parse_list_input(text)
    elif field == "languages":
        user_details["languages"] = parse_list_input(text)
    # Answers about one role or project are placed on that entry (core/profile_synthesis.py:_place_answer).

    overrides = user_details.setdefault("supplement_overrides", {})
    if isinstance(overrides, dict):
        overrides[field] = text

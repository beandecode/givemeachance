from __future__ import annotations

import json
import re
from typing import Any

from adapters.llm import get_llm
from core.parsing import is_core_high_field
from core.profile_quality import compute_profile_completeness as _compute_completeness_score
from core.repositories.profiles import insert_candidate_profile
from core.schemas import Settings

# Technical names that are never ordinary words, so a nurse's "lymph node" or "react to" adds no false skill.
_SKILL_HINTS: list[tuple[str, str]] = [
    ("python", "Python"),
    ("typescript", "TypeScript"),
    ("javascript", "JavaScript"),
    ("sql", "SQL"),
    ("flask", "Flask"),
    ("django", "Django"),
    ("fastapi", "FastAPI"),
    ("react.js", "React"),
    ("reactjs", "React"),
    ("node.js", "Node.js"),
    ("nodejs", "Node.js"),
    ("docker", "Docker"),
    ("kubernetes", "Kubernetes"),
    ("aws", "AWS"),
    ("gcp", "GCP"),
    ("microsoft azure", "Azure"),
    ("azure devops", "Azure"),
    ("airflow", "Airflow"),
    ("pyspark", "Spark"),
    ("apache spark", "Spark"),
    ("tensorflow", "TensorFlow"),
    ("pytorch", "PyTorch"),
    ("machine learning", "Machine Learning"),
    ("llm", "LLM"),
]


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _split_outside_brackets(text: str) -> list[str]:
    pieces, depth, current = [], 0, ""
    for char in text:
        depth += char in "(["
        depth -= char in ")]" and depth > 0
        if char in ",;|" and depth == 0:
            pieces.append(current)
            current = ""
        else:
            current += char
    return [piece.strip() for piece in [*pieces, current] if piece.strip()]


def _split_text_tokens(value: str) -> list[str]:
    """One entry per line; a line is split further only when it reads as a list ("Python, SQL, AWS").

    A sentence such as "Rebuilt ETL jobs with retries, idempotent loads and alerting; on-time delivery rose to 99.6%"
    or "Registered Nurse (College of Nurses of Ontario, 2021)" stays whole: a piece longer than three words, or a
    separator inside brackets, means it is not a list.
    """
    result: list[str] = []
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        pieces = _split_outside_brackets(line)
        if len(pieces) > 1 and all(len(piece.split()) <= 3 for piece in pieces):
            result.extend(pieces)
        else:
            result.append(line)
    return result


def _normalize_string_list(value: Any, limit: int = 50, split: bool = True) -> list[str]:
    """`split=False` for fields whose every entry is one thing (a bullet, a degree, a credential): never cut them."""
    if value is None:
        return []

    items: list[str] = []
    if isinstance(value, str):
        items = _split_text_tokens(value) if split else [line.strip() for line in value.splitlines() if line.strip()]
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                items.extend(_split_text_tokens(item) if split else [item.strip()])
            elif isinstance(item, dict):
                if "name" in item:
                    items.append(_clean_text(item.get("name")))
                elif "title" in item:
                    items.append(_clean_text(item.get("title")))
                else:
                    items.append(_clean_text(item))
            else:
                items.append(_clean_text(item))
    else:
        items = [_clean_text(value)]

    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _clean_text(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def _extract_skills_from_text(*texts: str) -> list[str]:
    merged = "\n".join([_clean_text(item) for item in texts]).lower()
    if not merged:
        return []
    result: list[str] = []
    for keyword, label in _SKILL_HINTS:
        # Whole words only: "node" must not match "nodes", "aws" must not match "laws", "react" not "reactive".
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", merged):
            result.append(label)
    return _normalize_string_list(result, limit=30)


def _without(items: list[str], other: list[str]) -> list[str]:
    """`items` minus entries that `other` already has (a model sometimes copies a bullet into both lists)."""
    seen = {text.strip(" .").casefold() for text in other}
    return [text for text in items if text.strip(" .").casefold() not in seen]


def _record_text(item: dict, keys: tuple[str, ...]) -> str:
    """Every part of an {"degree": ..., "school": ..., "years": ...} record, joined with " - "."""
    parts = [_clean_text(item.get(key)) for key in keys]
    parts += [_clean_text(value) for key, value in item.items() if key not in keys and isinstance(value, str | int)]
    return " - ".join(part for part in parts if part and not _is_unknown_text(part))


def _normalize_experiences(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    items: list[dict[str, Any]] = []
    for entry in raw[:12]:
        if not isinstance(entry, dict):
            continue

        title = _clean_text(entry.get("title"), "Experience")
        company = _clean_text(entry.get("company"), "unknown")
        start_date = _clean_text(entry.get("start_date"), "")
        end_date = _clean_text(entry.get("end_date"), "")
        duration = _clean_text(entry.get("duration"), "")
        if not duration:
            duration = f"{start_date or 'unknown'} - {end_date or 'present'}" if (start_date or end_date) else "unknown"

        items.append(
            {
                "title": title,
                "company": company,
                "location": _clean_text(entry.get("location"), "unknown"),
                "employment_type": _clean_text(entry.get("employment_type"), "unknown"),
                "start_date": start_date or "unknown",
                "end_date": end_date or "unknown",
                "duration": duration,
                "highlights": _normalize_string_list(entry.get("highlights"), limit=10, split=False),
                "achievements": _without(
                    _normalize_string_list(entry.get("achievements"), limit=6, split=False),
                    _normalize_string_list(entry.get("highlights"), limit=10, split=False),
                ),
                "tech_stack": _normalize_string_list(entry.get("tech_stack"), limit=12),
            }
        )
    return items


def _normalize_projects(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    items: list[dict[str, Any]] = []
    for entry in raw[:12]:
        if not isinstance(entry, dict):
            continue
        name = _clean_text(entry.get("name"))
        if not name:
            continue
        items.append(
            {
                "name": name,
                "role": _clean_text(entry.get("role"), "unknown"),
                "duration": _clean_text(entry.get("duration"), "unknown"),
                "summary": _clean_text(entry.get("summary"), ""),
                "impact": _normalize_string_list(entry.get("impact"), limit=5, split=False),
                "tech_stack": _normalize_string_list(entry.get("tech_stack"), limit=10),
                "links": _normalize_string_list(entry.get("links"), limit=6),
            }
        )
    return items


def _normalize_missing_information(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []

    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw[:20]:
        if not isinstance(entry, dict):
            continue
        field = _clean_text(entry.get("field"), "unknown_field")
        question = _clean_text(entry.get("question") or entry.get("reason"), "Please provide missing details.")
        priority = _clean_text(entry.get("priority"), "medium").lower()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        # Keep high-priority prompts only for true gating fields.
        if priority == "high" and not is_core_high_field(field):
            priority = "medium"
        key = field.casefold()  # one question per field: the model's and the app's own questions overlap
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "field": field,
                "question": question,
                "priority": priority,
            }
        )
    return items


def _is_unknown_text(value: Any) -> bool:
    text = _clean_text(value).strip().lower()
    return text in {"", "unknown", "n/a", "na", "none", "null", "not provided", "not available"}


def without_placeholders(value: Any) -> Any:
    """Copy of a profile with placeholder strings ("unknown", "n/a", ...) and emptied containers removed.

    Stored profiles keep placeholders so gaps stay visible; text sent for document generation
    must not, or the model may copy "unknown" into a resume.
    """
    if isinstance(value, dict):
        cleaned = {key: without_placeholders(item) for key, item in value.items()}
        return {key: item for key, item in cleaned.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        cleaned_items = [without_placeholders(item) for item in value]
        return [item for item in cleaned_items if item not in (None, "", [], {})]
    if isinstance(value, str) and _is_unknown_text(value):
        return None
    return value


def _parse_experience_date_hint(value: str) -> tuple[str | None, str | None]:
    text = _clean_text(value)
    if not text:
        return None, None

    # "2020-01", "2020/1" or "2020" keep their month when given: "Jan 2020" style is left to the model.
    years = [
        f"{year}-{int(month):02d}" if month and 1 <= int(month) <= 12 else year
        for year, month in re.findall(r"((?:19|20)\d{2})(?:[-/.](\d{1,2})(?!\d))?", text)
    ]
    start_date = years[0] if years else None
    end_date = None
    if len(years) >= 2:
        end_date = years[1]
    elif re.search(r"present|current|now|至今", text, flags=re.IGNORECASE):
        end_date = "present"

    return start_date, end_date


def _merge_supplement_answers(profile: dict[str, Any], input_bundle: dict[str, Any]) -> set[str]:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    contact = identity.get("contact") if isinstance(identity.get("contact"), dict) else {}
    if not isinstance(contact.get("links"), list):
        contact["links"] = []

    preferences = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
    experiences = profile.get("experiences") if isinstance(profile.get("experiences"), list) else []
    education = profile.get("education") if isinstance(profile.get("education"), list) else []
    certifications = profile.get("certifications") if isinstance(profile.get("certifications"), list) else []
    languages = profile.get("languages") if isinstance(profile.get("languages"), list) else []
    core_skills = profile.get("core_skills") if isinstance(profile.get("core_skills"), list) else []

    user_details = input_bundle.get("user_details") if isinstance(input_bundle.get("user_details"), dict) else {}
    supplement_answers = (
        input_bundle.get("supplement_answers") if isinstance(input_bundle.get("supplement_answers"), dict) else {}
    )
    legacy_overrides = (
        user_details.get("supplement_overrides") if isinstance(user_details.get("supplement_overrides"), dict) else {}
    )

    merged_answers: dict[str, str] = {}
    for source in (legacy_overrides, supplement_answers):
        for raw_field, raw_answer in source.items():
            field = _clean_text(raw_field)
            answer = _clean_text(raw_answer)
            if field and answer:
                merged_answers[field] = answer

    def _append_unique(base: list[str], incoming: list[str], limit: int) -> list[str]:
        merged = _normalize_string_list(base + incoming, limit=limit, split=False)  # both sides are clean already
        return merged

    # Keep additional structured details from supplement-friendly user_details keys.
    contact["links"] = _append_unique(
        contact.get("links", []), _normalize_string_list(user_details.get("links"), limit=12), limit=12
    )
    profile["education"] = _append_unique(
        education, _normalize_string_list(user_details.get("education_items"), limit=10, split=False), limit=10
    )
    profile["certifications"] = _append_unique(
        certifications, _normalize_string_list(user_details.get("certifications"), limit=12, split=False), limit=12
    )
    profile["languages"] = _append_unique(
        languages, _normalize_string_list(user_details.get("languages"), limit=8), limit=8
    )

    answered_fields: set[str] = set()
    for field, answer in merged_answers.items():
        answered_fields.add(field)

        if field == "identity.name":
            identity["name"] = answer
        elif field == "identity.current_title":
            identity["current_title"] = answer
        elif field == "identity.location":
            identity["location"] = answer
        elif field == "identity.years_experience":
            identity["years_experience"] = answer
        elif field == "identity.contact.email":
            contact["email"] = answer
        elif field == "identity.contact.phone":
            contact["phone"] = answer
        elif field in {"identity.contact.links", "links"}:
            contact["links"] = _append_unique(
                contact.get("links", []), _normalize_string_list(answer, limit=12), limit=12
            )
        elif field == "core_skills":
            profile["core_skills"] = _append_unique(core_skills, _normalize_string_list(answer, limit=24), limit=24)
        elif field == "preferences.target_roles":
            preferences["target_roles"] = _append_unique(
                preferences.get("target_roles", []), _normalize_string_list(answer, limit=10), limit=10
            )
        elif field == "preferences.preferred_locations":
            preferences["preferred_locations"] = _append_unique(
                preferences.get("preferred_locations", []), _normalize_string_list(answer, limit=10), limit=10
            )
        elif field == "preferences.work_authorization":
            preferences["work_authorization"] = answer
        elif field == "education":
            profile["education"] = _append_unique(
                profile.get("education", []), _normalize_string_list(answer, limit=10, split=False), limit=10
            )
        elif field == "certifications":
            profile["certifications"] = _append_unique(
                profile.get("certifications", []), _normalize_string_list(answer, limit=12, split=False), limit=12
            )
        elif field == "languages":
            profile["languages"] = _append_unique(
                profile.get("languages", []), _normalize_string_list(answer, limit=8), limit=8
            )
        elif field.startswith(("experiences[", "projects[")):
            _place_answer(profile, field, answer, input_bundle.get("previous_profile"))
        # Answers without a list position ("experiences") reach the model as context and are placed by it.

    identity["contact"] = contact
    profile["identity"] = identity
    profile["preferences"] = preferences
    profile["experiences"] = experiences

    return answered_fields


_LIST_PATH = re.compile(r"^(experiences|projects)\[(\d+)\](?:\.(\w+))?")


def _entry_key(entry: Any, kind: str) -> str:
    if not isinstance(entry, dict):
        return ""
    names = ("title", "company") if kind == "experiences" else ("name",)
    return " | ".join(_clean_text(entry.get(name)).casefold() for name in names)


def _find_entry(profile: dict[str, Any], kind: str, index: int, previous: Any) -> dict[str, Any] | None:
    """The entry an answer's path points to; the position refers to the profile the question was asked about."""
    entries = profile.get(kind) if isinstance(profile.get(kind), list) else []
    old_entries = previous.get(kind) if isinstance(previous, dict) and isinstance(previous.get(kind), list) else []
    if index < len(old_entries):
        key = _entry_key(old_entries[index], kind)
        for entry in entries:
            if key and _entry_key(entry, kind) == key:
                return entry
    return entries[index] if index < len(entries) and isinstance(entries[index], dict) else None


def _place_answer(profile: dict[str, Any], field: str, answer: str, previous: Any) -> None:
    """Put an answer about one role or project on that entry: dates as dates, anything else as a result bullet."""
    match = _LIST_PATH.match(field)
    if not match:
        return
    kind, index, attribute = match.group(1), int(match.group(2)), match.group(3) or ""
    entry = _find_entry(profile, kind, index, previous)
    if entry is None:
        return
    if attribute in {"start_date", "end_date", "duration"}:
        start_hint, end_hint = _parse_experience_date_hint(answer)
        entry["start_date"] = start_hint or entry.get("start_date", "unknown")
        entry["end_date"] = end_hint or entry.get("end_date", "unknown")
        entry["duration"] = answer if _is_unknown_text(entry.get("duration")) else entry["duration"]
        return
    target = "impact" if kind == "projects" else "achievements"
    bullets = entry.get(target) if isinstance(entry.get(target), list) else []
    if not any(answer.casefold() in str(bullet).casefold() for bullet in bullets):
        bullets.append(answer)
    entry[target] = bullets


def _union(base: list[Any], incoming: list[Any]) -> list[Any]:
    seen = {str(item).casefold() for item in base}
    return base + [item for item in incoming if str(item).casefold() not in seen and not _is_unknown_text(item)]


def _keep_previous_facts(profile: dict[str, Any], previous: Any) -> None:
    """A rebuilt profile never loses a fact of the profile it replaces (a hand edit, an earlier answer).

    The model is asked to keep everything, but a model can drop or merge entries; this puts back every role, project,
    bullet and list item it left out, and every known identity or preference value it turned into unknown.
    """
    if not isinstance(previous, dict):
        return
    for kind, lists in (
        ("experiences", ("highlights", "achievements", "tech_stack")),
        ("projects", ("impact", "tech_stack")),
    ):
        entries = profile.get(kind) if isinstance(profile.get(kind), list) else []
        for old in previous.get(kind) or []:
            if not isinstance(old, dict):
                continue
            key = _entry_key(old, kind)
            new = next((entry for entry in entries if _entry_key(entry, kind) == key), None)
            if new is None:
                entries.append(old)
                continue
            for name in lists:
                new[name] = _union(list(new.get(name) or []), list(old.get(name) or []))
            for name, value in old.items():
                if isinstance(value, str) and _is_unknown_text(new.get(name)) and not _is_unknown_text(value):
                    new[name] = value
        profile[kind] = entries
    for name in ("career_highlights", "core_skills", "education", "certifications", "languages"):
        profile[name] = _union(list(profile.get(name) or []), list(previous.get(name) or []))
    matrix, old_matrix = profile.get("skill_matrix") or {}, previous.get("skill_matrix") or {}
    if isinstance(matrix, dict) and isinstance(old_matrix, dict):
        for name, values in old_matrix.items():
            if isinstance(values, list):
                matrix[name] = _union(list(matrix.get(name) or []), values)
    for section in ("identity", "preferences"):
        new_section, old_section = profile.get(section), previous.get(section)
        if not isinstance(new_section, dict) or not isinstance(old_section, dict):
            continue
        for name, value in old_section.items():
            if isinstance(value, list):
                new_section[name] = _union(list(new_section.get(name) or []), value)
            elif isinstance(value, str) and not _is_unknown_text(value) and _is_unknown_text(new_section.get(name)):
                new_section[name] = value
    if not _is_unknown_text(previous.get("profile_summary")) and _is_unknown_text(profile.get("profile_summary")):
        profile["profile_summary"] = previous["profile_summary"]


def _is_missing_field_resolved(profile: dict[str, Any], field: str, answered_fields: set[str] | None = None) -> bool:
    normalized_field = _clean_text(field)
    if not normalized_field:
        return False
    if answered_fields and normalized_field in answered_fields:
        return True

    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    contact = identity.get("contact") if isinstance(identity.get("contact"), dict) else {}
    preferences = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
    experiences = profile.get("experiences") if isinstance(profile.get("experiences"), list) else []

    if normalized_field == "identity.name":
        return not _is_unknown_text(identity.get("name"))
    if normalized_field == "identity.current_title":
        return not _is_unknown_text(identity.get("current_title"))
    if normalized_field == "identity.location":
        return not _is_unknown_text(identity.get("location"))
    if normalized_field == "identity.years_experience":
        return not _is_unknown_text(identity.get("years_experience"))
    if normalized_field == "identity.contact.email":
        return not _is_unknown_text(contact.get("email"))
    if normalized_field == "identity.contact.phone":
        return not _is_unknown_text(contact.get("phone"))
    if normalized_field in {"identity.contact.links", "links"}:
        return bool(_normalize_string_list(contact.get("links"), limit=12))
    if normalized_field == "core_skills":
        return bool(profile.get("core_skills"))
    if normalized_field == "education":
        return bool(profile.get("education"))
    if normalized_field == "certifications":
        return bool(profile.get("certifications"))
    if normalized_field == "languages":
        return bool(profile.get("languages"))
    if normalized_field == "preferences.target_roles":
        return bool(preferences.get("target_roles"))
    if normalized_field == "preferences.preferred_locations":
        return bool(preferences.get("preferred_locations"))
    if normalized_field == "preferences.work_authorization":
        return not _is_unknown_text(preferences.get("work_authorization"))
    if normalized_field == "experiences":
        return bool(experiences)
    if normalized_field.startswith("experiences") and (
        "start_date" in normalized_field or "end_date" in normalized_field
    ):
        return any(
            isinstance(item, dict)
            and (
                (not _is_unknown_text(item.get("start_date")) and not _is_unknown_text(item.get("end_date")))
                or (
                    not _is_unknown_text(item.get("duration"))
                    and any(ch.isdigit() for ch in _clean_text(item.get("duration")))
                )
            )
            for item in experiences
        )
    if normalized_field.startswith("experiences"):
        return bool(experiences)

    return False


def _build_default_profile_summary(
    identity_name: str, core_skills: list[str], resume_text: str, extra_context: str
) -> str:
    name = identity_name if identity_name != "unknown" else "Candidate"
    skill_text = ", ".join(core_skills[:6])
    if skill_text:
        return f"{name} with strengths in {skill_text}."

    merged = _clean_text(f"{resume_text}\n{extra_context}")
    if merged:
        return merged[:320]
    return "Candidate profile synthesized from user inputs."


def _build_missing_prompts(profile: dict[str, Any]) -> list[dict[str, str]]:
    generated: list[dict[str, str]] = []

    identity = profile.get("identity", {}) if isinstance(profile.get("identity"), dict) else {}
    contact = identity.get("contact", {}) if isinstance(identity.get("contact"), dict) else {}
    preferences = profile.get("preferences", {}) if isinstance(profile.get("preferences"), dict) else {}
    experiences = profile.get("experiences", []) if isinstance(profile.get("experiences"), list) else []
    has_dates = any(
        isinstance(item, dict)
        and (
            (not _is_unknown_text(item.get("start_date")) and not _is_unknown_text(item.get("end_date")))
            or (
                not _is_unknown_text(item.get("duration"))
                and any(ch.isdigit() for ch in _clean_text(item.get("duration")))
            )
        )
        for item in experiences
    )

    if _is_unknown_text(identity.get("name")):
        generated.append(
            {
                "field": "identity.name",
                "question": "What name should appear on your documents?",
                "priority": "high",
            }
        )
    if not profile.get("core_skills"):
        generated.append(
            {
                "field": "core_skills",
                "question": "List your 5–10 strongest skills: the methods, tools or licences your field asks for.",
                "priority": "high",
            }
        )
    if not experiences:
        generated.append(
            {
                "field": "experiences",
                "question": "Describe at least one job or project: what you did and what it achieved.",
                "priority": "high",
            }
        )
    elif not has_dates:
        generated.append(
            {
                "field": "experiences[].start_date/end_date",
                "question": "When did each key role start and end? Dates are used to match experience requirements.",
                "priority": "medium",
            }
        )
    else:
        undated = [
            (index, item)
            for index, item in enumerate(experiences)
            if isinstance(item, dict) and _is_unknown_text(item.get("start_date"))
        ]
        for index, item in undated[:2]:
            role = " at ".join(
                part for part in (_clean_text(item.get("title")), _clean_text(item.get("company"))) if part
            )
            generated.append(
                {
                    "field": f"experiences[{index}].start_date",
                    "question": f"When did you work as {role}? Write the start and end, for example 2018-05 - 2018-08.",
                    "priority": "low",
                }
            )
    if not profile.get("education"):
        generated.append(
            {
                "field": "education",
                "question": "What is your education (school, degree, years)?",
                "priority": "medium",
            }
        )
    if not preferences.get("target_roles"):
        generated.append(
            {
                "field": "preferences.target_roles",
                "question": "Which roles are you targeting (2–3 is ideal)?",
                "priority": "medium",
            }
        )
    if _is_unknown_text(preferences.get("work_authorization")):
        generated.append(
            {
                "field": "preferences.work_authorization",
                "question": "What is your work authorization (e.g. citizen, permanent resident, open work permit)?",
                "priority": "medium",
            }
        )
    if not contact.get("links"):
        generated.append(
            {
                "field": "identity.contact.links",
                "question": "Add a link to your LinkedIn, portfolio or other professional page.",
                "priority": "low",
            }
        )
    if not preferences.get("preferred_locations"):
        generated.append(
            {
                "field": "preferences.preferred_locations",
                "question": "Where do you want to work (e.g. Toronto, Remote – Canada)?",
                "priority": "low",
            }
        )
    if _is_unknown_text(contact.get("email")) and _is_unknown_text(contact.get("phone")):
        generated.append(
            {
                "field": "identity.contact.email",
                "question": "Add at least one way to contact you (email or phone).",
                "priority": "low",
            }
        )

    return generated


def _normalize_master_profile(
    raw_profile: dict[str, Any], input_bundle: dict[str, Any], attachments: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    profile = raw_profile if isinstance(raw_profile, dict) else {}

    resume_text = _clean_text(input_bundle.get("resume_text"))
    extra_context = _clean_text(input_bundle.get("extra_context"))
    links = _normalize_string_list(input_bundle.get("links"), limit=12)

    user_details = input_bundle.get("user_details") if isinstance(input_bundle.get("user_details"), dict) else {}

    parsed_skills = _extract_skills_from_text(resume_text, extra_context, _clean_text(user_details.get("key_skills")))

    skill_matrix_raw = profile.get("skill_matrix") if isinstance(profile.get("skill_matrix"), dict) else {}
    skill_matrix = {
        "languages": _normalize_string_list(skill_matrix_raw.get("languages"), limit=10),
        "frameworks": _normalize_string_list(skill_matrix_raw.get("frameworks"), limit=10),
        "cloud": _normalize_string_list(skill_matrix_raw.get("cloud"), limit=10),
        "data": _normalize_string_list(skill_matrix_raw.get("data"), limit=10),
        "devops": _normalize_string_list(skill_matrix_raw.get("devops"), limit=10),
        "tools": _normalize_string_list(skill_matrix_raw.get("tools"), limit=10),
        "professional_skills": _normalize_string_list(skill_matrix_raw.get("professional_skills"), limit=12),
        "domains": _normalize_string_list(skill_matrix_raw.get("domains"), limit=10),
    }

    core_skills = _normalize_string_list(profile.get("core_skills"), limit=24)
    seen_skills = {skill.casefold() for skill in core_skills}
    # The model's own skills come first; a keyword list only fills in what it missed (whole words, technical names).
    model_skills = skill_matrix["professional_skills"] + skill_matrix["tools"] + skill_matrix["languages"]
    model_skills += skill_matrix["frameworks"] + skill_matrix["cloud"]
    for skill in model_skills + parsed_skills:
        if skill.casefold() not in seen_skills:
            seen_skills.add(skill.casefold())
            core_skills.append(skill)
        if len(core_skills) >= 24:
            break

    experiences = _normalize_experiences(profile.get("experiences"))
    projects = _normalize_projects(profile.get("projects"))

    education_items = profile.get("education")
    if isinstance(education_items, list):
        education = _normalize_string_list(
            [
                item
                if isinstance(item, str)
                else _record_text(item, ("degree", "field", "school", "institution", "dates", "years", "honors", "gpa"))
                if isinstance(item, dict)
                else _clean_text(item)
                for item in education_items
            ],
            limit=10,
            split=False,
        )
    else:
        education = []

    certifications = _normalize_string_list(
        [
            _record_text(item, ("name", "issuer", "year", "date")) if isinstance(item, dict) else item
            for item in (profile.get("certifications") if isinstance(profile.get("certifications"), list) else [])
        ],
        limit=12,
        split=False,
    )

    raw_identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    raw_contact = raw_identity.get("contact") if isinstance(raw_identity.get("contact"), dict) else {}

    identity = {
        # What the candidate typed in the form wins over what the model read or guessed.
        "name": _clean_text(user_details.get("candidate_name") or raw_identity.get("name"), "unknown"),
        "current_title": _clean_text(user_details.get("current_title") or raw_identity.get("current_title"), "unknown"),
        "location": _clean_text(user_details.get("location") or raw_identity.get("location"), "unknown"),
        "years_experience": _clean_text(
            user_details.get("years_experience") or raw_identity.get("years_experience"), "unknown"
        ),
        "contact": {
            "email": _clean_text(user_details.get("email") or raw_contact.get("email"), "unknown"),
            "phone": _clean_text(user_details.get("phone") or raw_contact.get("phone"), "unknown"),
            "links": _normalize_string_list(raw_contact.get("links"), limit=12),
        },
    }
    for link in links:
        if link not in identity["contact"]["links"]:
            identity["contact"]["links"].append(link)

    preferences_raw = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
    preferences = {
        "target_roles": _normalize_string_list(
            user_details.get("target_roles") or preferences_raw.get("target_roles"), limit=10
        ),
        "preferred_locations": _normalize_string_list(
            user_details.get("preferred_locations") or preferences_raw.get("preferred_locations"), limit=10
        ),
        "employment_types": _normalize_string_list(preferences_raw.get("employment_types"), limit=6),
        "work_authorization": _clean_text(
            user_details.get("work_authorization") or preferences_raw.get("work_authorization"), "unknown"
        ),
    }

    evidence_notes = _normalize_string_list(profile.get("evidence_notes"), limit=20)
    for item in attachments[:8]:
        name = _clean_text(item.get("name"), "file")
        mime = _clean_text(item.get("mime_type"), "application/octet-stream")
        note = f"Attachment: {name} ({mime})"
        if note not in evidence_notes:
            evidence_notes.append(note)
    for link in identity["contact"]["links"][:6]:
        note = f"Link: {link}"
        if note not in evidence_notes:
            evidence_notes.append(note)

    profile_summary = _clean_text(profile.get("profile_summary"))
    if not profile_summary:
        profile_summary = _build_default_profile_summary(identity["name"], core_skills, resume_text, extra_context)

    normalized = {
        "identity": identity,
        "profile_summary": profile_summary,
        "career_highlights": _normalize_string_list(profile.get("career_highlights"), limit=8, split=False),
        "core_skills": core_skills,
        "skill_matrix": skill_matrix,
        "experiences": experiences,
        "projects": projects,
        "education": education,
        "certifications": certifications,
        "languages": _normalize_string_list(profile.get("languages"), limit=8),
        "preferences": preferences,
        "evidence_notes": evidence_notes,
    }

    _keep_previous_facts(normalized, input_bundle.get("previous_profile"))
    answered_fields = _merge_supplement_answers(normalized, input_bundle)

    existing_missing = [
        item
        for item in _normalize_missing_information(profile.get("missing_information"))
        if not _is_missing_field_resolved(normalized, item.get("field", ""), answered_fields=answered_fields)
    ]
    generated_missing = _build_missing_prompts(normalized)
    normalized["missing_information"] = _normalize_missing_information(existing_missing + generated_missing)

    raw_confidence = profile.get("field_confidence")
    if isinstance(raw_confidence, list):
        field_confidence: list[dict[str, Any]] = []
        for item in raw_confidence[:20]:
            if not isinstance(item, dict):
                continue
            field = _clean_text(item.get("field"), "unknown")
            try:
                conf = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
            except (TypeError, ValueError):
                conf = 0.5
            reason = _clean_text(item.get("reason"), "")
            field_confidence.append({"field": field, "confidence": conf, "reason": reason})
    else:
        field_confidence = [
            {
                "field": "core_skills",
                "confidence": 0.85 if normalized["core_skills"] else 0.2,
                "reason": "Derived from model output and user input text.",
            },
            {
                "field": "experiences",
                "confidence": 0.8 if normalized["experiences"] else 0.25,
                "reason": "Higher when structured timeline and highlights exist.",
            },
            {
                "field": "education",
                "confidence": 0.75 if normalized["education"] else 0.3,
                "reason": "Based on explicit candidate inputs and attachment evidence.",
            },
        ]
    normalized["field_confidence"] = field_confidence

    computed_score = _compute_completeness_score(normalized)
    normalized["completeness_score"] = computed_score
    normalized["completeness_score_source"] = "application_field_coverage_v1"
    normalized["model_name"] = _clean_text(profile.get("model_name"), model_name)

    return normalized


def synthesize_master_profile(
    conn,
    settings: Settings,
    input_bundle: dict[str, Any],
    attachments: list[dict[str, Any]],
    quota_subject: str | None = None,
    profile_user_id: int | None = None,
) -> dict:
    """Synthesize and persist a master profile from structured text + optional files."""
    evaluator = get_llm(settings, quota_subject=quota_subject)

    master_profile = evaluator.synthesize_master_profile(
        input_bundle=input_bundle,
        attachments=attachments,
    )
    normalized_profile = _normalize_master_profile(
        raw_profile=master_profile,
        input_bundle=input_bundle,
        attachments=attachments,
        model_name=settings.llm.model,
    )

    row = insert_candidate_profile(
        conn,
        source_bundle_json=json.dumps(
            {
                "input_bundle": input_bundle,
                "attachments_meta": [
                    {
                        "name": item.get("name", "file"),
                        "mime_type": item.get("mime_type", "application/octet-stream"),
                        "size": int(item.get("size", 0)),
                    }
                    for item in attachments
                ],
            },
            ensure_ascii=False,
        ),
        master_profile_json=json.dumps(normalized_profile, ensure_ascii=False),
        model_name=str(normalized_profile.get("model_name", settings.llm.model)),
        user_id=profile_user_id,
    )

    return {
        "profile_id": int(row["id"]),
        "profile_version": int(row["profile_version"]),
        "model_name": str(row["model_name"]),
        "master_profile": normalized_profile,
    }

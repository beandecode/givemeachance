from __future__ import annotations

import base64
import binascii
import json

from flask import Request

from core.errors import UserFacingError, failure_summary
from core.generate_resume import parse_master_profile_row
from core.profile_synthesis import synthesize_master_profile
from core.repositories.profiles import get_candidate_profile, get_latest_candidate_profile
from core.request_normalization import (
    apply_supplement_answer,
    normalize_user_details,
    parse_list_input,
)

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_UPLOAD_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", DOCX_TYPE}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_SIZE = 30 * 1024 * 1024


class ProfileInputError(UserFacingError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = str(message)
        self.status_code = int(status_code)


def build_profile_synthesis_inputs(
    request: Request,
    *,
    allowed_upload_types: set[str],
    max_file_size: int,
    max_total_size: int,
) -> tuple[dict, list[dict]]:
    attachments: list[dict] = []

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ProfileInputError("JSON body must be an object", 400)
    payload_user_details = payload.get("user_details") if isinstance(payload.get("user_details"), dict) else {}
    input_bundle = {
        "resume_text": str(payload.get("resume_text", "")).strip(),
        "extra_context": str(payload.get("extra_context", "")).strip(),
        "links": parse_list_input(payload.get("links", [])),
        "user_details": {
            "candidate_name": str(
                payload_user_details.get("candidate_name", payload.get("candidate_name", ""))
            ).strip(),
            "current_title": str(payload_user_details.get("current_title", payload.get("current_title", ""))).strip(),
            "location": str(payload_user_details.get("location", payload.get("location", ""))).strip(),
            "years_experience": str(
                payload_user_details.get("years_experience", payload.get("years_experience", ""))
            ).strip(),
            "email": str(payload_user_details.get("email", payload.get("email", ""))).strip(),
            "phone": str(payload_user_details.get("phone", payload.get("phone", ""))).strip(),
            "work_authorization": str(
                payload_user_details.get("work_authorization", payload.get("work_authorization", ""))
            ).strip(),
            "target_roles": parse_list_input(payload_user_details.get("target_roles", payload.get("target_roles", []))),
            "preferred_locations": parse_list_input(
                payload_user_details.get("preferred_locations", payload.get("preferred_locations", []))
            ),
            "key_skills": str(payload_user_details.get("key_skills", payload.get("key_skills", ""))).strip(),
        },
    }
    raw_attachments = payload.get("attachments", [])
    if not isinstance(raw_attachments, list):
        raise ProfileInputError("attachments must be an array", 400)
    total_size = 0
    for item in raw_attachments:
        if not isinstance(item, dict):
            raise ProfileInputError("each attachment must be an object", 400)
        mime_type = str(item.get("mime_type", "application/octet-stream")).lower()
        if mime_type not in allowed_upload_types:
            raise ProfileInputError(f"unsupported file type: {mime_type}", 400)
        encoded = item.get("data_base64", "")
        if not isinstance(encoded, str):
            raise ProfileInputError("attachment data_base64 must be a string", 400)
        if len(encoded) > 4 * ((max_file_size + 2) // 3):
            raise ProfileInputError("file too large", 413)
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ProfileInputError("invalid attachment base64", 400) from exc
        size = len(decoded)
        if size > max_file_size:
            raise ProfileInputError("file too large", 413)
        total_size += size
        if total_size > max_total_size:
            raise ProfileInputError("total upload size exceeds limit", 413)
        if not size:
            continue
        if mime_type == DOCX_TYPE:
            # The model cannot read Word files, so their text joins the pasted résumé text.
            text = docx_text(decoded)
            input_bundle["resume_text"] = "\n\n".join(part for part in (input_bundle["resume_text"], text) if part)
            continue
        attachments.append(
            {
                "name": str(item.get("name", "file")),
                "mime_type": mime_type,
                "size": size,
                "data_base64": encoded,
            }
        )

    return input_bundle, attachments


def docx_text(data: bytes) -> str:
    """The text of a Word document: paragraphs in order, then table cells (many résumé templates use tables)."""
    import io
    import zipfile

    from docx import Document

    try:
        document = Document(io.BytesIO(data))
    except (ValueError, KeyError, zipfile.BadZipFile) as exc:
        raise ProfileInputError("the Word file could not be read; save it again as .docx or attach a PDF", 400) from exc
    lines = [paragraph.text.strip() for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells: list[str] = []
            for cell in row.cells:
                text = cell.text.strip()
                if text and text not in cells:  # merged cells repeat their text
                    cells.append(text)
            lines.append(" | ".join(cells))
    return "\n".join(line for line in lines if line)


def validate_profile_synthesis_inputs(input_bundle: dict, attachments: list[dict]) -> None:
    user_details = input_bundle.get("user_details") if isinstance(input_bundle.get("user_details"), dict) else {}
    has_user_details = any(str(value).strip() for value in user_details.values() if not isinstance(value, list)) or any(
        bool(value) for value in user_details.values() if isinstance(value, list)
    )

    if (
        not input_bundle.get("resume_text")
        and not input_bundle.get("extra_context")
        and not attachments
        and not has_user_details
    ):
        raise ProfileInputError("provide resume_text/extra_context, structured user_details, or attachments", 400)


def run_profile_synthesis(
    conn,
    settings,
    *,
    input_bundle: dict,
    attachments: list[dict],
    quota_subject: str,
    profile_user_id: int,
    allowed_upload_types: set[str],
) -> dict:
    try:
        result = synthesize_master_profile(
            conn,
            settings=settings,
            input_bundle=input_bundle,
            attachments=attachments,
            quota_subject=quota_subject,
            profile_user_id=profile_user_id,
        )
    except Exception as error:
        raise ProfileInputError(f"profile synthesis failed: {failure_summary(error)}", 502) from error

    return {
        "profile_id": result["profile_id"],
        "profile_version": result["profile_version"],
        "model_name": result["model_name"],
        "master_profile": result["master_profile"],
        "source": {
            "input_type": "multipart" if attachments else "json",
            "attachment_count": len(attachments),
            "accepted_types": sorted(allowed_upload_types),
        },
    }


def run_profile_supplement(
    conn,
    settings,
    *,
    payload: dict,
    profile_scope_user_id: int | None,
    actor_user_id: int,
    quota_subject: str,
) -> dict:
    profile_id_raw = payload.get("profile_id")
    selected_fields = parse_list_input(payload.get("selected_fields", []))
    answers_raw = payload.get("answers", {}) if isinstance(payload.get("answers"), dict) else {}
    additional_context = str(payload.get("additional_context", "")).strip()

    if not selected_fields:
        raise ProfileInputError("selected_fields is required", 400)

    if profile_id_raw is not None:
        try:
            target_profile = get_candidate_profile(conn, int(profile_id_raw), user_id=profile_scope_user_id)
        except (TypeError, ValueError) as exc:
            raise ProfileInputError("invalid profile_id", 400) from exc
        if target_profile is None:
            raise ProfileInputError("profile_id not found", 404)
    else:
        target_profile = get_latest_candidate_profile(conn, user_id=profile_scope_user_id)

    if target_profile is None:
        raise ProfileInputError("no profile available for supplementation", 404)

    try:
        source_bundle = json.loads(str(target_profile["source_bundle_json"] or "{}"))
    except json.JSONDecodeError:
        source_bundle = {}

    base_input_bundle = source_bundle.get("input_bundle") if isinstance(source_bundle, dict) else {}
    if not isinstance(base_input_bundle, dict):
        base_input_bundle = {}

    base_user_details = normalize_user_details(base_input_bundle.get("user_details"))
    latest_profile_payload = parse_master_profile_row(target_profile) or {}

    missing_map: dict[str, dict] = {}
    missing_items = (
        latest_profile_payload.get("missing_information")
        if isinstance(latest_profile_payload.get("missing_information"), list)
        else []
    )
    for item in missing_items:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip()
        if field:
            missing_map[field] = item

    supplement_lines: list[str] = []
    answered_count = 0
    supplement_answers: dict[str, str] = {}
    for field in selected_fields:
        answer = str(answers_raw.get(field, "")).strip()
        if not answer:
            continue

        missing_item = missing_map.get(field, {})
        question = str(missing_item.get("question", "")).strip()
        if question:
            supplement_lines.append(f"- {field}: {answer} (question: {question})")
        else:
            supplement_lines.append(f"- {field}: {answer}")
        apply_supplement_answer(base_user_details, field, answer)
        supplement_answers[field] = answer
        answered_count += 1

    if not additional_context and answered_count == 0:
        raise ProfileInputError("provide at least one non-empty answer or additional_context", 400)

    if additional_context:
        supplement_lines.append(f"- additional_context: {additional_context}")

    base_extra_context = str(base_input_bundle.get("extra_context", "")).strip()
    merged_sections = [section for section in [base_extra_context] if section]
    if supplement_lines:
        merged_sections.append("Supplemented details from user selection:\n" + "\n".join(supplement_lines))
    merged_extra_context = "\n\n".join(merged_sections)

    # The whole current profile, hand edits included: the files it was first built from are not kept, so this is
    # the only full record of the candidate. Bookkeeping fields are left out.
    profile_context = {
        key: value
        for key, value in latest_profile_payload.items()
        if key
        not in {
            "missing_information",
            "field_confidence",
            "completeness_score",
            "completeness_score_source",
            "model_name",
            "evidence_notes",
        }
    }

    input_bundle = {
        "resume_text": str(base_input_bundle.get("resume_text", "")).strip(),
        "extra_context": merged_extra_context,
        "links": parse_list_input(base_input_bundle.get("links", [])),
        "user_details": base_user_details,
        "previous_profile": profile_context,
        "supplement_answers": supplement_answers,
    }

    try:
        result = synthesize_master_profile(
            conn,
            settings=settings,
            input_bundle=input_bundle,
            attachments=[],
            quota_subject=quota_subject,
            profile_user_id=actor_user_id,
        )
    except Exception as error:
        raise ProfileInputError(f"profile supplementation failed: {failure_summary(error)}", 502) from error

    return {
        "profile_id": result["profile_id"],
        "profile_version": result["profile_version"],
        "model_name": result["model_name"],
        "master_profile": result["master_profile"],
        "source": {
            "input_type": "supplement",
            "base_profile_id": int(target_profile["id"]),
            "selected_count": len(selected_fields),
            "answered_count": answered_count,
        },
    }

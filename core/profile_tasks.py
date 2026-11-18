"""Background tasks that build Master Profile versions with the LLM."""

from __future__ import annotations

import json

from core.config import load_settings
from core.db import db_conn
from core.errors import UserFacingError
from core.profile_input_service import ALLOWED_UPLOAD_TYPES, run_profile_supplement, run_profile_synthesis
from core.user_scope import quota_subject_for_user
from core.users import get_user_by_id


def _owner(conn, owner_user_id: int):
    user_row = get_user_by_id(conn, int(owner_user_id))
    if user_row is None or not int(user_row["is_active"]):
        raise UserFacingError("task owner not found")
    return user_row


def _scrub_attachment_data(task_id: str, payload: dict) -> None:
    """Uploaded files are only needed for the LLM call; don't keep megabytes of base64 in the task row."""
    attachments = payload.get("attachments") or []
    if not attachments:
        return
    kept = {**payload, "attachments": [{k: v for k, v in item.items() if k != "data_base64"} for item in attachments]}
    with db_conn(load_settings().app.db_path) as conn:
        conn.execute("UPDATE async_tasks SET payload_json = ? WHERE task_id = ?", (json.dumps(kept), task_id))


def run_synthesize_profile_task(task_id: str, payload: dict, owner_user_id: int, correlation_id: str, report_progress):
    settings = load_settings()
    try:
        report_progress("synthesizing", 30, "building the Master Profile")
        with db_conn(settings.app.db_path) as conn:
            user_row = _owner(conn, owner_user_id)
            result = run_profile_synthesis(
                conn,
                settings,
                input_bundle=payload["input_bundle"],
                attachments=payload.get("attachments") or [],
                quota_subject=quota_subject_for_user(user_row),
                profile_user_id=int(user_row["id"]),
                allowed_upload_types=ALLOWED_UPLOAD_TYPES,
            )
        report_progress("persisted", 95, "profile version saved")
    finally:
        _scrub_attachment_data(task_id, payload)
    return {"profile_id": result["profile_id"], "profile_version": result["profile_version"]}


def run_supplement_profile_task(task_id: str, payload: dict, owner_user_id: int, correlation_id: str, report_progress):
    settings = load_settings()
    report_progress("supplementing", 30, "adding answers to the Master Profile")
    with db_conn(settings.app.db_path) as conn:
        user_row = _owner(conn, owner_user_id)
        result = run_profile_supplement(
            conn,
            settings,
            payload=payload,
            profile_scope_user_id=int(user_row["id"]),
            actor_user_id=int(user_row["id"]),
            quota_subject=quota_subject_for_user(user_row),
        )
    report_progress("persisted", 95, "profile version saved")
    return {"profile_id": result["profile_id"], "profile_version": result["profile_version"]}

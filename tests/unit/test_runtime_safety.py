import base64
from pathlib import Path

import pytest
from flask import Flask, request

from core.async_tasks import LocalTaskRunner, create_async_task, get_async_task, mark_task_running, request_cancel_task
from core.config import load_settings
from core.db import db_conn, init_db
from core.generate_cl import persist_cover_letter
from core.generate_resume import persist_generated_resume
from core.ingest import run_ingest
from core.profile_input_service import ProfileInputError, build_profile_synthesis_inputs


@pytest.mark.parametrize(
    "attachments,expected",
    [
        ([{"data_base64": "not-base64!"}], 400),
        ([{"data_base64": base64.b64encode(b"x" * 11).decode(), "size": 0}], 413),
        ([{"data_base64": base64.b64encode(b"x" * 8).decode()}] * 2, 413),
        ({"data_base64": ""}, 400),
    ],
)
def test_json_attachment_limits_use_actual_bytes(attachments, expected):
    if isinstance(attachments, list):
        attachments = [{"mime_type": "application/pdf", **item} for item in attachments]
    app = Flask(__name__)
    with app.test_request_context("/", json={"attachments": attachments}):
        with pytest.raises(ProfileInputError) as error:
            build_profile_synthesis_inputs(
                request, allowed_upload_types={"application/pdf"}, max_file_size=10, max_total_size=12
            )
    assert error.value.status_code == expected


def test_ingest_enforces_total_limit_across_sources():
    current = load_settings()
    settings = current.model_copy(update={"pipeline": current.pipeline.model_copy(update={"daily_limit": 2})})
    init_db(settings.app.db_path)
    with db_conn(settings.app.db_path) as conn:
        result = run_ingest(conn, settings, "limit-test")
    assert result["inserted_count"] == 2


def test_documents_are_versioned_per_job_and_not_written_to_disk():
    settings = load_settings()
    init_db(settings.app.db_path)
    with db_conn(settings.app.db_path) as conn:
        ids = run_ingest(conn, settings, "artifact-test")["inserted_job_ids"][:2]
        for persist in (persist_generated_resume, persist_cover_letter):
            outputs = [persist(conn, settings.app.db_path, job_id, f"document-{job_id}", None) for job_id in ids]
            assert [(output["job_id"], output["version"]) for output in outputs] == [(ids[0], 1), (ids[1], 1)]
            assert all("file" not in output for output in outputs)
    output_dir = Path(settings.app.db_path).parent
    assert not (output_dir / "resumes").exists() and not (output_dir / "cover_letters").exists()


def test_task_claim_is_conditional_and_queued_cancel_is_final():
    settings = load_settings()
    init_db(settings.app.db_path)
    with db_conn(settings.app.db_path) as conn:
        task = create_async_task(conn, "manual_search", 1, {}, "claim-test")
        assert mark_task_running(conn, task["task_id"]) is True
        assert mark_task_running(conn, task["task_id"]) is False
        other = create_async_task(conn, "manual_search", 1, {}, "cancel-test")
        request_cancel_task(conn, other["task_id"])
        assert mark_task_running(conn, other["task_id"]) is False
        assert get_async_task(conn, other["task_id"])["state"] == "cancelled"


def test_late_cancel_preserves_successful_committed_result():
    settings = load_settings()
    init_db(settings.app.db_path)
    with db_conn(settings.app.db_path) as conn:
        task = create_async_task(conn, "manual_search", 1, {}, "late-cancel-test")
    runner = LocalTaskRunner(settings.app.db_path)

    def handler(task_id, payload, user_id, correlation_id, progress):
        with db_conn(settings.app.db_path) as conn:
            request_cancel_task(conn, task_id)
        progress("persisted", 95, "committed output")
        return {"artifact": "saved"}

    runner.enqueue(task["task_id"], handler)
    runner.shutdown()
    with db_conn(settings.app.db_path) as conn:
        assert get_async_task(conn, task["task_id"])["state"] == "succeeded"


def test_cancel_before_side_effect_stage_stops_handler():
    settings = load_settings()
    init_db(settings.app.db_path)
    with db_conn(settings.app.db_path) as conn:
        task = create_async_task(conn, "manual_search", 1, {}, "early-cancel-test")
    runner = LocalTaskRunner(settings.app.db_path)
    effects = []

    def handler(task_id, payload, user_id, correlation_id, progress):
        with db_conn(settings.app.db_path) as conn:
            request_cancel_task(conn, task_id)
        progress("generating", 65, "about to generate")
        effects.append("should not run")
        return {}

    runner.enqueue(task["task_id"], handler)
    runner.shutdown()
    assert effects == []
    with db_conn(settings.app.db_path) as conn:
        assert get_async_task(conn, task["task_id"])["state"] == "cancelled"

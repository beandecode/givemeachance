import pytest
from flask import Flask, request

from core.config import load_settings
from core.db import db_conn, init_db
from core.profile_input_service import (
    ProfileInputError,
    build_profile_synthesis_inputs,
    run_profile_supplement,
    validate_profile_synthesis_inputs,
)


def test_validate_profile_synthesis_inputs_requires_content():
    try:
        validate_profile_synthesis_inputs(
            {
                "resume_text": "",
                "extra_context": "",
                "user_details": {},
            },
            [],
        )
        pytest.fail("expected ProfileInputError")
    except ProfileInputError as exc:
        assert exc.status_code == 400
        assert "provide resume_text/extra_context" in exc.message


def test_build_profile_synthesis_inputs_from_json_payload():
    app = Flask(__name__)
    with app.test_request_context(
        "/api/v1/profile/synthesize",
        method="POST",
        json={
            "resume_text": "Python SQL",
            "links": "https://github.com/example\nhttps://portfolio.example.com",
            "user_details": {
                "candidate_name": "Alex",
                "target_roles": "Backend Engineer, Platform Engineer",
            },
        },
    ):
        input_bundle, attachments = build_profile_synthesis_inputs(
            request=request,
            allowed_upload_types={"application/pdf", "image/png", "image/jpeg", "image/webp"},
            max_file_size=10 * 1024 * 1024,
            max_total_size=30 * 1024 * 1024,
        )

    assert input_bundle["resume_text"] == "Python SQL"
    assert input_bundle["links"] == ["https://github.com/example", "https://portfolio.example.com"]
    assert input_bundle["user_details"]["candidate_name"] == "Alex"
    assert input_bundle["user_details"]["target_roles"] == ["Backend Engineer", "Platform Engineer"]
    assert attachments == []


def test_run_profile_supplement_requires_selected_fields():
    settings = load_settings()
    init_db(settings.app.db_path)

    with db_conn(settings.app.db_path) as conn:
        try:
            run_profile_supplement(
                conn,
                settings,
                payload={"selected_fields": []},
                profile_scope_user_id=1,
                actor_user_id=1,
                quota_subject="user:1",
            )
            pytest.fail("expected ProfileInputError")
        except ProfileInputError as exc:
            assert exc.status_code == 400
            assert exc.message == "selected_fields is required"

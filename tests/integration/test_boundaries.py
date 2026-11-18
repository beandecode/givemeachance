"""HTTP boundaries: auth, request shape, owner isolation, readiness gates and the route inventory."""

import json
from pathlib import Path

import pytest

from app import create_app
from core.config import load_settings
from core.db import db_conn
from tests.conftest import patch_llm_settings
from tests.support import (
    application_row,
    approved_profile,
    finish,
    generate,
    register,
    search,
    set_application,
    synthesize_profile,
    top_job,
)


def test_signed_out_requests_are_not_authenticated():
    client = create_app().test_client()
    assert client.get("/api/v1/session").get_json()["data"] == {"user": None}
    with client.session_transaction() as session:
        assert "user_id" not in session
    assert client.get("/api/v1/jobs").status_code == 401
    assert client.post("/api/v1/searches", json={}).status_code == 401
    assert client.put("/api/v1/search-preferences", json={"adzuna": {}}).status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/session"),
        ("POST", "/api/v1/account"),
        ("POST", "/api/v1/profile/synthesize"),
        ("POST", "/api/v1/profile/supplement"),
        ("POST", "/api/v1/profile/1/review"),
        ("POST", "/api/v1/searches"),
        ("POST", "/api/v1/evaluations/rerun"),
        ("POST", "/api/v1/jobs/manual"),
        ("POST", "/api/v1/jobs/1/documents"),
        ("PATCH", "/api/v1/jobs/1/application"),
        ("PUT", "/api/v1/search-preferences"),
    ],
)
@pytest.mark.parametrize("body", [[], "bad", 42, None])
def test_non_object_json_never_causes_500(method, path, body):
    client = register(create_app())
    response = client.open(path, method=method, data=json.dumps(body), content_type="application/json")
    assert response.status_code == 400
    assert response.is_json
    assert response.headers["X-Correlation-ID"] == response.get_json()["correlation_id"]


def test_origin_and_json_content_type_boundary():
    client = register(create_app())
    assert client.delete("/api/v1/session", headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert (
        client.post("/api/v1/profile/1/review", data='{"review_status":"approved"}', content_type="text/plain")
    ).status_code == 415
    assert client.delete("/api/v1/session", headers={"Origin": "http://localhost"}).status_code == 200


def test_workspace_personal_resources_and_pagination():
    app = create_app()
    first = register(app, "boundary_first")
    second = register(app, "boundary_second")
    approved_profile(app, first)
    search(app, first)
    listing = first.get("/api/v1/jobs?limit=1").get_json()["data"]
    assert listing["total"] == 3
    assert len(listing["items"]) == 1
    next_page = first.get("/api/v1/jobs?limit=1&offset=1").get_json()["data"]
    assert listing["items"][0]["id"] != next_page["items"][0]["id"]
    assert second.get("/api/v1/jobs").get_json()["data"]["items"] == []
    assert second.get("/api/v1/profile").get_json()["data"]["profile"] is None
    with db_conn(load_settings().app.db_path) as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE username = 'boundary_second'")
    assert second.get("/api/v1/jobs").get_json()["data"]["items"] == []
    profile = first.get("/api/v1/profile").get_json()["data"]["profile"]
    assert "source_bundle_json" not in profile
    assert "master_profile" in profile
    overview = first.get("/api/v1/overview").get_json()["data"]
    assert overview["counts"]["jobs"] == 3
    assert "guided_workflow" not in overview


def test_search_preferences_json_validation_and_user_isolation():
    app = create_app()
    first = register(app, "preference_first")
    second = register(app, "preference_second")
    endpoint = "/api/v1/search-preferences"
    assert first.put(endpoint, json={"adzuna": {"salary_min": 100, "salary_max": 10}}).status_code == 400
    assert first.put(endpoint, json={"adzuna": {"days_old": -1}}).status_code == 400
    response = first.put(endpoint, json={"adzuna": {"location": "Ottawa", "results_per_page": 99}})
    assert response.status_code == 200
    assert response.get_json()["data"]["config"]["adzuna"]["results_per_page"] == 10
    assert first.get(endpoint).get_json()["data"]["source"] == "user"
    assert second.get(endpoint).get_json()["data"]["source"] == "default"


def test_pending_profile_cannot_generate_or_force_search():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    job_id = top_job(client)

    pending = synthesize_profile(app, client)  # newest version, not approved yet
    for kind in ("resume", "cover_letter"):
        task, _ = generate(app, client, job_id, kind, state="failed")
        assert task["error_message_safe"]

    with db_conn(load_settings().app.db_path) as conn:
        row = conn.execute(
            "SELECT master_profile_json FROM candidate_profiles WHERE id = ?", (pending["profile_id"],)
        ).fetchone()
        payload = json.loads(row[0])
        payload["missing_information"] = [{"field": "experiences", "priority": "high", "question": "Provide dates"}]
        conn.execute(
            "UPDATE candidate_profiles SET master_profile_json = ? WHERE id = ?",
            (json.dumps(payload), pending["profile_id"]),
        )
    task, _ = finish(
        app,
        client,
        client.post("/api/v1/evaluations/rerun", json={"force_when_high_missing": True}),
        state="failed",
    )
    assert task["error_message_safe"]


def test_invalid_requests_never_enqueue_a_task():
    app = create_app()
    client = register(app)
    for path, body in [
        ("/api/v1/jobs/1/documents", {"kind": "poem"}),
        ("/api/v1/jobs/manual", {"title": "x"}),
        ("/api/v1/evaluations/rerun", {"limit": -1}),
        ("/api/v1/profile/synthesize", {}),
        ("/api/v1/profile/supplement", {"selected_fields": []}),
    ]:
        assert client.post(path, json=body).status_code in {400, 404}, path
    assert client.get("/api/v1/tasks").get_json()["data"]["total"] == 0


def test_query_bounds_and_request_limit():
    app = create_app()
    client = register(app)
    assert client.get("/api/v1/jobs?limit=bad").status_code == 400
    assert client.get("/api/v1/jobs?limit=100000").status_code == 400
    app.config["MAX_CONTENT_LENGTH"] = 32
    response = client.post("/api/v1/profile/synthesize", json={"resume_text": "x" * 64})
    assert response.status_code == 413
    assert response.is_json


def test_regeneration_preserves_application_progress():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    job_id = top_job(client)
    set_application(client, job_id, "interview", "Interview on Friday")

    generate(app, client, job_id, "cover_letter")

    application = application_row(client, job_id)
    assert application["status"] == "interview"
    assert application["note"] == "Interview on Friday"


def test_route_inventory_matches_registered_endpoints():
    inventory = json.loads((Path(__file__).resolve().parents[2] / "docs/route-inventory.json").read_text())
    app = create_app()
    expected = {(r["method"], r["path"], r["endpoint"]) for r in inventory}
    actual = {
        (method, rule.rule, rule.endpoint)
        for rule in app.url_map.iter_rules()
        for method in rule.methods - {"HEAD", "OPTIONS"}
    }
    assert actual == expected


def test_live_search_requires_a_profile_before_provider_calls(monkeypatch):
    app = create_app()
    client = register(app)
    patch_llm_settings(monkeypatch, provider="gemini_api")
    task, _ = finish(app, client, client.post("/api/v1/searches", json={}), state="failed")
    assert task["error_message_safe"]
    assert client.get("/api/v1/jobs").get_json()["data"]["total"] == 0


def test_live_evaluation_uses_personal_profile_even_with_legacy_flag_disabled(monkeypatch):
    import adapters.llm.gemini_api as gemini_api
    from adapters.llm.mock_gemini import MockGeminiEvaluator

    app = create_app()
    client = register(app)
    profile = approved_profile(app, client)
    patch_llm_settings(monkeypatch, provider="gemini_api", fullstack_enabled=False)
    # Keep every external call mocked while exercising the live-provider branch.
    monkeypatch.setattr(gemini_api, "GeminiApiEvaluator", lambda **kwargs: MockGeminiEvaluator(kwargs["model_name"]))
    search(app, client)
    match = client.get(f"/api/v1/jobs/{top_job(client)}").get_json()["data"]["match"]
    assert match["source_profile_id"] == profile["profile_id"]

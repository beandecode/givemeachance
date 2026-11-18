import pytest

from app import create_app
from tests.conftest import patch_llm_settings
from tests.support import approved_profile, finish, generate, register, search, top_job


@pytest.fixture
def evaluated_job(monkeypatch):
    patch_llm_settings(monkeypatch, fullstack_enabled=True)
    app = create_app()
    client = register(app, "consistency_user")
    profile = approved_profile(app, client, candidate_name="Consistent Candidate")
    search(app, client)
    return app, client, top_job(client), profile


def _detail(client, job_id):
    return client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]


@pytest.mark.parametrize("kind", ["resume", "cover_letter"])
def test_profile_change_requires_new_matching_before_generation(evaluated_job, kind):
    app, client, job_id, _ = evaluated_job
    # A different skill set changes what the scorer sees, so the old match no longer describes this candidate.
    newest = approved_profile(app, client, key_skills="Rust, Go, Kubernetes, Terraform")

    blocked, _ = generate(app, client, job_id, kind, state="failed")
    assert "different profile version" in blocked["error_message_safe"]
    assert _detail(client, job_id)["documents"][kind] is None

    finish(app, client, client.post("/api/v1/evaluations/rerun", json={"job_ids": [job_id]}))
    assert _detail(client, job_id)["match_uses_latest_profile"] is True
    generate(app, client, job_id, kind)

    detail = _detail(client, job_id)
    assert detail["match"]["source_profile_id"] == newest["profile_id"]
    document = client.get(f"/api/v1/documents/{kind}/{detail['documents'][kind]['id']}").get_json()["data"]
    assert document["source_profile_id"] == newest["profile_id"]


@pytest.mark.parametrize("kind", ["resume", "cover_letter"])
def test_a_correction_the_scorer_cannot_see_keeps_the_match_valid(evaluated_job, kind):
    app, client, job_id, _ = evaluated_job
    approved_profile(app, client, candidate_name="Casey Chen-Smith")  # only the name differs

    assert _detail(client, job_id)["match_uses_latest_profile"] is True
    generate(app, client, job_id, kind)  # no re-evaluation needed, no Gemini call spent


def test_re_evaluation_with_same_profile_invalidates_old_decision(evaluated_job):
    app, client, job_id, _ = evaluated_job
    generate(app, client, job_id, "resume")
    assert _detail(client, job_id)["decision"]["generate_resume"] is True

    finish(app, client, client.post("/api/v1/evaluations/rerun", json={"job_ids": [job_id]}))

    decision = _detail(client, job_id)["decision"]
    assert decision["viewed_match_at"] is None
    assert decision["generate_resume"] is False
    assert decision["generate_cover_letter"] is False

from app import create_app
from tests.support import approve_profile, approved_profile, register


def _client(app, username=None):
    return register(app, username, prefix="jobs_api")


def _approved_profile(client):
    approved_profile(client.application, client, candidate_name="Api User")


def _finish_tasks(app):
    app.extensions["task_runner"].drain()


def _jobs(client, query=""):
    response = client.get(f"/api/v1/jobs{query}")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def test_search_task_then_filter_sort_and_detail():
    app = create_app()
    client = _client(app)
    _approved_profile(client)

    started = client.post("/api/v1/searches", json={})
    assert started.status_code == 202
    task_id = started.get_json()["data"]["task_id"]
    _finish_tasks(app)
    assert client.get(f"/api/v1/tasks/{task_id}").get_json()["data"]["state"] == "succeeded"

    everything = _jobs(client)
    assert everything["total"] > 0
    by_score = [item["match_score"] for item in _jobs(client, "?sort=score&limit=100")["items"]]
    assert by_score == sorted(by_score, reverse=True)
    top = by_score[0]
    assert all(item["match_score"] >= top for item in _jobs(client, f"?min_score={top}")["items"])
    first = everything["items"][0]
    assert _jobs(client, f"?q={first['company'][:4]}")["total"] >= 1
    assert _jobs(client, "?status=interview")["total"] == 0

    detail = client.get(f"/api/v1/jobs/{first['id']}").get_json()["data"]
    assert detail["description"]
    assert detail["match"]["total_score"] == first["match_score"]
    assert detail["match_uses_latest_profile"] is True
    assert detail["documents"] == {"resume": None, "cover_letter": None}


def test_jobs_of_other_users_are_not_visible():
    app = create_app()
    owner = _client(app, "jobs_owner")
    _approved_profile(owner)
    owner.post("/api/v1/searches", json={})
    _finish_tasks(app)
    job_id = _jobs(owner)["items"][0]["id"]

    stranger = _client(app, "jobs_stranger")
    response = stranger.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 404
    assert response.get_json()["error_code"] == 3003
    assert stranger.post(f"/api/v1/jobs/{job_id}/archive").status_code == 404


def test_archive_hides_job_until_unarchived():
    app = create_app()
    client = _client(app)
    _approved_profile(client)
    client.post("/api/v1/searches", json={})
    _finish_tasks(app)
    job_id = _jobs(client)["items"][0]["id"]
    total = _jobs(client)["total"]

    archived = client.post(f"/api/v1/jobs/{job_id}/archive").get_json()["data"]
    assert archived["archived_at"]
    assert _jobs(client)["total"] == total - 1
    assert _jobs(client, "?include_archived=true")["total"] == total

    client.delete(f"/api/v1/jobs/{job_id}/archive")
    assert _jobs(client)["total"] == total


def test_pasted_job_description_is_added_and_evaluated():
    app = create_app()
    client = _client(app)
    _approved_profile(client)

    started = client.post(
        "/api/v1/jobs/manual",
        json={"title": "Platform Engineer", "company": "Northwind", "description": "Python, AWS and Kubernetes."},
    )
    assert started.status_code == 202
    _finish_tasks(app)

    items = _jobs(client, "?q=Northwind")["items"]
    assert [item["title"] for item in items] == ["Platform Engineer"]
    assert items[0]["match_score"] is not None


def test_pasted_job_requires_description():
    client = _client(create_app())

    response = client.post("/api/v1/jobs/manual", json={"title": "No description"})

    assert response.status_code == 400
    assert response.get_json()["details"][0]["field"] == "description"


def test_pasted_job_needs_an_approved_profile(monkeypatch):
    import adapters.llm.gemini_api as gemini_api
    from adapters.llm.mock_gemini import MockGeminiEvaluator
    from tests.conftest import patch_llm_settings
    from tests.support import finish, synthesize_profile

    patch_llm_settings(monkeypatch, provider="gemini_api")
    monkeypatch.setattr(gemini_api, "GeminiApiEvaluator", lambda **kwargs: MockGeminiEvaluator(kwargs["model_name"]))
    app = create_app()
    client = _client(app)
    body = {"title": "Backend Engineer", "description": "Build Python APIs with Flask and SQL."}

    profile = synthesize_profile(app, client)  # pending: not approved yet
    task, _ = finish(app, client, client.post("/api/v1/jobs/manual", json=body), state="failed")
    assert "approved" in task["error_message_safe"]

    approve_profile(client, profile["profile_id"])
    _, result = finish(app, client, client.post("/api/v1/jobs/manual", json=body))
    assert int(result["job_id"]) >= 1


def test_each_evaluation_records_the_prompt_version_that_produced_it():
    from core.config import load_settings
    from core.db import db_conn

    app = create_app()
    client = _client(app)
    _approved_profile(client)
    client.post("/api/v1/searches", json={})
    _finish_tasks(app)

    with db_conn(load_settings().app.db_path) as conn:
        versions = {row[0] for row in conn.execute("SELECT prompt_version FROM evaluations")}
        fingerprints = [row[0] for row in conn.execute("SELECT source_profile_fingerprint FROM evaluations")]

    assert versions == {load_settings().llm.prompt_version} == {"v3"}
    assert fingerprints and all(len(fp) == 64 for fp in fingerprints)


def _searched_job(app, client):
    _approved_profile(client)
    client.post("/api/v1/searches", json={})
    _finish_tasks(app)
    return _jobs(client)["items"][0]["id"]


def test_a_pasted_full_description_replaces_the_preview_and_can_be_scored():
    from core.config import load_settings
    from core.db import db_conn

    app = create_app()
    client = _client(app)
    job_id = _searched_job(app, client)
    with db_conn(load_settings().app.db_path) as conn:  # the mock board returns whole postings; make this one a preview
        conn.execute("UPDATE jobs SET description = ? WHERE id = ?", ("Build APIs and " + "x" * 484 + "…", job_id))
    assert client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]["description_is_snippet"] is False  # mock source

    with db_conn(load_settings().app.db_path) as conn:
        conn.execute("UPDATE jobs SET source = 'adzuna' WHERE id = ?", (job_id,))
    assert client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]["description_is_snippet"] is True

    full = "Backend engineer: Python, Flask, SQL and AWS. " * 12
    saved = client.put(f"/api/v1/jobs/{job_id}/description", json={"description": full})
    assert saved.status_code == 200
    detail = saved.get_json()["data"]
    assert detail["description"] == full.strip() and detail["description_is_snippet"] is False

    rerun = client.post("/api/v1/evaluations/rerun", json={"job_ids": [job_id]})
    assert rerun.status_code == 202
    _finish_tasks(app)
    assert client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]["match"] is not None


def test_years_asked_are_read_from_the_current_text_in_the_list_and_the_detail():
    app = create_app()
    client = _client(app)
    job_id = _searched_job(app, client)
    full = "Backend engineer for our platform team. " * 6 + "You have 3 to 5 years of experience with Python. " * 2
    assert client.put(f"/api/v1/jobs/{job_id}/description", json={"description": full}).status_code == 200

    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    assert (detail["years_asked_min"], detail["years_asked_max"]) == (3, 5)
    row = next(item for item in _jobs(client, "?limit=100")["items"] if item["id"] == job_id)
    assert (row["years_asked_min"], row["years_asked_max"]) == (3, 5)
    assert "description" not in row

    plain = "Backend engineer: Python, Flask, SQL and AWS. " * 12
    client.put(f"/api/v1/jobs/{job_id}/description", json={"description": plain})
    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    assert (detail["years_asked_min"], detail["years_asked_max"]) == (None, None)


def test_the_description_must_be_the_whole_posting_and_belong_to_the_user():
    app = create_app()
    owner = _client(app)
    job_id = _searched_job(app, owner)
    stranger = _client(app)

    too_short = owner.put(f"/api/v1/jobs/{job_id}/description", json={"description": "short"})
    assert (too_short.status_code, too_short.get_json()["error_code"]) == (400, 2002)
    assert stranger.put(f"/api/v1/jobs/{job_id}/description", json={"description": "y" * 300}).status_code == 404
    assert owner.put("/api/v1/jobs/999999/description", json={"description": "y" * 300}).status_code == 404

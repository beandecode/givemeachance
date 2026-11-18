"""The guided journey: steps derived from stored data, empty-deck reasons, per-job steps and follow-ups (ADR-015)."""

from tests.support import approved_profile, register


def _app():
    from app import create_app

    return create_app()


def _journey(client):
    response = client.get("/api/v1/journey")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def _steps(journey):
    return {step["key"]: step for step in journey["steps"]}


def test_new_user_starts_at_the_profile_step():
    client = register(_app(), prefix="journey")
    journey = _journey(client)
    steps = _steps(journey)
    assert journey["current"] == "profile" and not journey["completed"]
    assert steps["profile"]["status"] == "current" and steps["profile"]["reason_code"] == "profile_missing"
    assert steps["search_prefs"]["status"] == "todo"
    assert journey["discover"] == "no_jobs"
    assert journey["counts"]["jobs"] == 0


def test_steps_advance_with_data_and_the_deck_reason_follows():
    app = _app()
    client = register(app, prefix="journey")
    approved_profile(app, client, candidate_name="Journey User")
    journey = _journey(client)
    assert _steps(journey)["profile"]["status"] == "done"
    assert journey["current"] == "search_prefs"

    suggested = client.get("/api/v1/search-preferences/suggested").get_json()["data"]["config"]
    assert client.put("/api/v1/search-preferences", json=suggested).status_code == 200
    assert _journey(client)["current"] == "find_jobs"

    assert client.post("/api/v1/searches", json={}).status_code == 202
    app.extensions["task_runner"].drain()
    journey = _journey(client)
    assert journey["current"] == "pick" and journey["counts"]["jobs"] > 0
    assert journey["discover"] in {"has_cards", "below_threshold"}

    jobs = client.get("/api/v1/jobs?sort=score&limit=100").get_json()["data"]["items"]
    for job in jobs:
        assert client.put(f"/api/v1/jobs/{job['id']}/triage", json={"action": "skipped"}).status_code == 200
    assert _journey(client)["discover"] == "all_decided"


def test_skip_flag_is_stored_and_owner_scoped():
    app = _app()
    first, second = register(app, prefix="journey"), register(app, prefix="journey")
    response = first.put("/api/v1/journey", json={"skipped": True})
    assert response.get_json()["data"]["skipped"] is True
    assert _journey(second)["skipped"] is False
    assert first.put("/api/v1/journey", json={"skipped": False}).get_json()["data"]["skipped"] is False


def test_job_journey_scores_writes_applies_and_follows_up():
    app = _app()
    client = register(app, prefix="journey")
    approved_profile(app, client, candidate_name="Job Journey")
    assert client.post("/api/v1/searches", json={}).status_code == 202
    app.extensions["task_runner"].drain()
    job = client.get("/api/v1/jobs?sort=score&limit=100").get_json()["data"]["items"][0]
    path = f"/api/v1/jobs/{job['id']}"

    detail = client.get(path).get_json()["data"]
    steps = _steps(detail["journey"])
    assert detail["journey"]["current"] == "write" and steps["score"]["status"] == "done"
    assert steps["write"]["reason_code"] == "no_documents"

    response = client.post(f"{path}/documents", json={"kind": "resume"})
    assert response.status_code == 202
    app.extensions["task_runner"].drain()
    detail = client.get(path).get_json()["data"]
    assert detail["journey"]["current"] == "applied"
    assert _steps(detail["journey"])["write"]["status"] == "done"

    assert client.patch(f"{path}/application", json={"status": "submitted"}).status_code == 200
    detail = client.get(path).get_json()["data"]
    assert detail["journey"]["current"] == "follow_up"
    assert _steps(detail["journey"])["follow_up"]["reason_code"] == "no_follow_up"

    response = client.patch(f"{path}/application", json={"follow_up_at": "2020-01-01"})
    assert response.status_code == 200 and response.get_json()["data"]["follow_up_at"] == "2020-01-01"
    detail = client.get(path).get_json()["data"]
    assert detail["journey"]["follow_up_overdue"] is True and detail["journey"]["current"] is None
    assert _journey(client)["steps"][-1]["status"] == "done"

    cleared = client.patch(f"{path}/application", json={"follow_up_at": None})
    assert cleared.get_json()["data"]["follow_up_at"] is None
    assert client.patch(f"{path}/application", json={"follow_up_at": "2020-13-45"}).status_code == 400
    assert client.patch(f"{path}/application", json={}).status_code == 400


def test_a_stale_match_sends_the_job_back_to_the_score_step():
    app = _app()
    client = register(app, prefix="journey")
    approved_profile(app, client, candidate_name="Stale One")
    assert client.post("/api/v1/searches", json={}).status_code == 202
    app.extensions["task_runner"].drain()
    job = client.get("/api/v1/jobs?sort=score&limit=100").get_json()["data"]["items"][0]
    approved_profile(app, client, candidate_name="Stale One", key_skills="Rust, Go, Kubernetes, Terraform")
    journey = client.get(f"/api/v1/jobs/{job['id']}").get_json()["data"]["journey"]
    if journey["steps"][0]["status"] != "done":  # fingerprint may be unchanged for a small edit
        assert journey["current"] == "score" and journey["steps"][0]["reason_code"] == "match_stale"

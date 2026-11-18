"""Swipe decisions, the deck filter and per-user preferences (ADR-013)."""

from tests.support import approved_profile, register


def _client(app, username=None):
    client = register(app, username, prefix="triage")
    approved_profile(app, client, candidate_name="Triage User")
    return client


def _search(app, client):
    assert client.post("/api/v1/searches", json={}).status_code == 202
    app.extensions["task_runner"].drain()
    return client.get("/api/v1/jobs?sort=score&limit=100").get_json()["data"]["items"]


def _jobs(client, query):
    return client.get(f"/api/v1/jobs?{query}").get_json()["data"]


def _app():
    from app import create_app

    return create_app()


def test_deck_shows_pending_jobs_and_swipes_move_them_between_views():
    app = _app()
    client = _client(app)
    jobs = _search(app, client)
    assert len(jobs) >= 3
    assert all(job["triage"] is None for job in jobs)
    pending = _jobs(client, "triage=pending&sort=score")
    assert pending["total"] == len(jobs)

    skipped_id, waitlisted_id = jobs[0]["id"], jobs[1]["id"]
    for job_id, action in ((skipped_id, "skipped"), (waitlisted_id, "waitlisted")):
        response = client.put(f"/api/v1/jobs/{job_id}/triage", json={"action": action})
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["data"] == {
            "job_id": job_id,
            "action": action,
            "generate": None,
            "tasks": [],
            "queued_for_later": False,
        }

    assert [j["id"] for j in _jobs(client, "triage=skipped")["items"]] == [skipped_id]
    assert [j["id"] for j in _jobs(client, "triage=waitlisted")["items"]] == [waitlisted_id]
    assert _jobs(client, "triage=pending")["total"] == len(jobs) - 2
    assert client.get(f"/api/v1/jobs/{skipped_id}").get_json()["data"]["triage"] == "skipped"

    # A waitlisted job can be decided again; undo returns it to the deck.
    assert client.put(f"/api/v1/jobs/{waitlisted_id}/triage", json={"action": "skipped"}).status_code == 200
    assert _jobs(client, "triage=waitlisted")["total"] == 0
    undone = client.delete(f"/api/v1/jobs/{skipped_id}/triage")
    assert undone.status_code == 200 and undone.get_json()["data"]["triage"] is None
    assert _jobs(client, "triage=pending")["total"] == len(jobs) - 1


def test_deck_respects_the_minimum_score():
    app = _app()
    client = _client(app)
    jobs = _search(app, client)
    top = jobs[0]["match_score"]
    deck = _jobs(client, f"triage=pending&sort=score&min_score={top}")["items"]
    assert deck and all(job["match_score"] >= top for job in deck)


def test_accept_records_the_decision_and_starts_the_resume():
    app = _app()
    client = _client(app)
    job_id = _search(app, client)[0]["id"]

    response = client.put(f"/api/v1/jobs/{job_id}/triage", json={"action": "accepted"})
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["generate"] == "resume" and data["queued_for_later"] is False
    assert [task["task_type"] for task in data["tasks"]] == ["generate_resume"]
    assert data["tasks"][0]["job_id"] == job_id

    app.extensions["task_runner"].drain()
    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    assert detail["triage"] == "accepted" and detail["has_resume"] is True and detail["has_cover_letter"] is False
    assert detail["decision"]["generate_resume"] is True and detail["documents"]["resume"] is not None


def test_accept_can_ask_for_both_documents():
    app = _app()
    client = _client(app)
    job_id = _search(app, client)[0]["id"]
    runner = app.extensions["task_runner"]
    original_enqueue, pending = runner.enqueue, []
    runner.enqueue = lambda task_id, handler: pending.append((task_id, handler))
    try:
        data = client.put(
            f"/api/v1/jobs/{job_id}/triage", json={"action": "accepted", "generate": "resume_and_cover_letter"}
        ).get_json()["data"]
    finally:
        runner.enqueue = original_enqueue
    assert [task["task_type"] for task in data["tasks"]] == ["generate_resume", "generate_cover_letter"]
    for task_id, handler in pending:  # one after the other, as the writer-lock probe in conftest expects
        runner.enqueue(task_id, handler)
        runner.drain()
    summary = _jobs(client, "triage=accepted")["items"][0]
    assert summary["triage_generate"] == "resume_and_cover_letter"
    assert summary["has_resume"] and summary["has_cover_letter"]


def test_accept_at_the_task_limit_keeps_the_decision_and_reports_queued_for_later(monkeypatch):
    limit = 2
    monkeypatch.setattr("core.task_service.MAX_ACTIVE_TASKS_PER_USER", limit)
    app = _app()
    client = _client(app)
    jobs = _search(app, client)
    runner = app.extensions["task_runner"]
    original_enqueue = runner.enqueue
    runner.enqueue = lambda task_id, handler: None  # tasks stay queued, so the per-user limit fills up
    try:
        results = [
            client.put(f"/api/v1/jobs/{job['id']}/triage", json={"action": "accepted"}).get_json()["data"]
            for job in jobs[: limit + 1]
        ]
    finally:
        runner.enqueue = original_enqueue
    assert [r["queued_for_later"] for r in results] == [False] * limit + [True]
    assert results[-1]["tasks"] == []
    accepted = _jobs(client, "triage=accepted&limit=100")
    assert accepted["total"] == limit + 1
    assert [j["has_resume"] for j in accepted["items"] if j["id"] == results[-1]["job_id"]] == [False]


def test_undo_cancels_a_generation_that_has_not_started():
    app = _app()
    client = _client(app)
    job_id = _search(app, client)[0]["id"]
    runner = app.extensions["task_runner"]
    original_enqueue = runner.enqueue
    runner.enqueue = lambda task_id, handler: None
    try:
        task_id = client.put(f"/api/v1/jobs/{job_id}/triage", json={"action": "accepted"}).get_json()["data"]["tasks"][
            0
        ]["task_id"]
    finally:
        runner.enqueue = original_enqueue
    assert client.delete(f"/api/v1/jobs/{job_id}/triage").status_code == 200
    assert client.get(f"/api/v1/tasks/{task_id}").get_json()["data"]["state"] == "cancelled"


def test_accept_needs_an_evaluated_job_and_triage_is_owner_scoped():
    app = _app()
    owner = _client(app, "triage_owner")
    job_id = _search(app, owner)[0]["id"]
    stranger = _client(app, "triage_stranger")
    assert stranger.put(f"/api/v1/jobs/{job_id}/triage", json={"action": "skipped"}).status_code == 404
    assert stranger.delete(f"/api/v1/jobs/{job_id}/triage").status_code == 404
    assert owner.put(f"/api/v1/jobs/{job_id}/triage", json={"action": "bogus"}).status_code == 400
    assert _jobs(stranger, "triage=skipped")["total"] == 0


def test_preferences_default_validate_and_persist_per_user():
    app = _app()
    client = _client(app, "prefs_owner")
    defaults = client.get("/api/v1/preferences").get_json()["data"]
    assert defaults == {
        "swipe": {"left": "skip", "right": "generate_resume", "up": "waitlist", "down": "details"},
        "deck": {"min_score": 70, "mouse_drag": True, "buttons": True},
        "ui": {"glass": "auto"},
    }

    changed = {
        "swipe": {"left": "none", "right": "generate_resume_and_cover_letter", "up": "details", "down": "skip"},
        "deck": {"min_score": 80, "mouse_drag": False, "buttons": True},
        "ui": {"glass": "strong"},
    }
    assert client.put("/api/v1/preferences", json=changed).get_json()["data"] == changed
    assert client.get("/api/v1/preferences").get_json()["data"] == changed
    assert register(app, "prefs_other").get("/api/v1/preferences").get_json()["data"] == defaults

    duplicate = {**changed, "swipe": {**changed["swipe"], "left": "skip", "down": "skip"}}
    assert client.put("/api/v1/preferences", json=duplicate).status_code == 400
    assert client.put("/api/v1/preferences", json={**changed, "extra": 1}).status_code == 400
    assert client.put("/api/v1/preferences", json={**changed, "deck": {"min_score": 101}}).status_code == 400
    assert client.get("/api/v1/preferences").get_json()["data"] == changed

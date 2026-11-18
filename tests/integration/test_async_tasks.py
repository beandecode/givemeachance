"""Task lifecycle through `/api/v1`: queued work reaches a terminal state and exposes a result and progress events."""

from app import create_app
from core.config import load_settings
from core.db import db_conn
from tests.support import approved_profile, finish, generate, register, search, top_job


def test_resume_generation_task_flow():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    job_id = top_job(client)

    task, result = generate(app, client, job_id, "resume")

    assert task["task_type"] == "generate_resume" and task["job_id"] == job_id
    assert result["task_type"] == "generate_resume"
    assert int(result["job_id"]) == job_id
    assert int(result["version"]) >= 1


def test_cover_letter_generation_task_flow():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    job_id = top_job(client)

    task, result = generate(app, client, job_id, "cover_letter")

    assert task["task_type"] == "generate_cover_letter"
    assert int(result["job_id"]) == job_id
    assert int(result["version"]) >= 1


def test_re_evaluate_task_flow():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    newest = approved_profile(app, client)

    _, result = finish(
        app, client, client.post("/api/v1/evaluations/rerun", json={"scope": "all", "decided_by": "test-suite"})
    )

    assert result["task_type"] == "re_evaluate"
    assert result["scope"] == "all"
    assert result["evaluated_count"] >= 1
    assert result["source_profile_version"] == newest["profile_version"]


def test_search_task_flow():
    app = create_app()
    client = register(app)
    approved_profile(app, client)

    _, result = finish(app, client, client.post("/api/v1/searches", json={"force_when_high_missing": False}))

    assert result["task_type"] == "manual_search"
    assert result["inserted_count"] >= 0
    assert result["evaluated_count"] >= 0


def test_pasted_job_task_flow():
    app = create_app()
    client = register(app)

    _, result = finish(
        app,
        client,
        client.post(
            "/api/v1/jobs/manual",
            json={
                "title": "Senior Backend Engineer",
                "description": "Build Python services, APIs, and data integrations with Flask and SQL.",
                "company": "ExampleCo",
                "location": "Toronto",
            },
        ),
    )

    assert result["task_type"] == "manual_jd_match"
    assert int(result["job_id"]) >= 1


def test_task_progress_events_are_recorded_in_order():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    task, _ = generate(app, client, top_job(client), "resume")

    with db_conn(load_settings().app.db_path) as conn:
        events = conn.execute(
            "SELECT event_type, progress_percent FROM task_events WHERE task_id = ? ORDER BY id", (task["task_id"],)
        ).fetchall()

    assert len(events) >= 2
    assert events[0]["event_type"] == "task_queued"
    assert events[-1]["progress_percent"] == 100
    assert [event["progress_percent"] for event in events] == sorted(event["progress_percent"] for event in events)


class _NeverRuns:
    """Task runner stand-in that leaves tasks queued."""

    def enqueue(self, task_id, handler):
        pass

    def shutdown(self, wait=True):
        pass


def test_the_same_request_while_it_is_still_active_returns_the_same_task():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    app.extensions["task_runner"] = _NeverRuns()

    first = client.post("/api/v1/searches", json={}).get_json()["data"]
    second = client.post("/api/v1/searches", json={}).get_json()["data"]
    different = client.post("/api/v1/searches", json={"force_when_high_missing": True})

    assert second["task_id"] == first["task_id"]
    # A search with other options would double the job-board requests: one search at a time per user.
    assert different.status_code == 409
    assert client.get("/api/v1/tasks?active=true").get_json()["data"]["total"] == 1


def test_each_user_may_have_only_three_active_tasks():
    app = create_app()
    client = register(app)
    other = register(app)
    app.extensions["task_runner"] = _NeverRuns()
    bodies = [{"title": f"Job {n}", "description": "Python"} for n in range(4)]

    statuses = [client.post("/api/v1/jobs/manual", json=body).status_code for body in bodies]

    assert statuses == [202, 202, 202, 429]
    assert other.post("/api/v1/jobs/manual", json=bodies[0]).status_code == 202

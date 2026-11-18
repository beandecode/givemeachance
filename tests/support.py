"""Helpers that drive the app through `/api/v1`, the same contract the web app uses."""

from __future__ import annotations

import os

DEFAULT_PASSWORD = "password123"
DEFAULT_DETAILS = {
    "candidate_name": "Test Candidate",
    "target_roles": ["Backend Engineer"],
    "key_skills": "Python, SQL, Flask, AWS",
}


def register(app, username: str | None = None, *, prefix: str = "user"):
    """A client signed in as a fresh account (sign-up is open under the test settings)."""
    client = app.test_client()
    username = username or f"{prefix}_{os.urandom(4).hex()}"
    response = client.post("/api/v1/account", json={"username": username, "password": DEFAULT_PASSWORD})
    assert response.status_code == 201, response.get_json()
    client.username = username
    return client


def finish(app, client, response, *, state: str = "succeeded"):
    """Wait for the task a 202 response started; return (task, result) once it reached `state`."""
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["task_id"]
    app.extensions["task_runner"].drain()
    task = client.get(f"/api/v1/tasks/{task_id}").get_json()["data"]
    assert task["state"] == state, task
    result = None
    if state == "succeeded":
        result = client.get(f"/api/v1/tasks/{task_id}/result").get_json()["data"]
    return task, result


def synthesize_profile(app, client, *, resume_text="Python TypeScript SQL Flask React AWS Docker", **details):
    """Build a new profile version; returns the task result (`profile_id`, `profile_version`, ...)."""
    body = {
        "resume_text": resume_text,
        "links": ["https://github.com/example"],
        "user_details": {**DEFAULT_DETAILS, **details},
    }
    return finish(app, client, client.post("/api/v1/profile/synthesize", json=body))[1]


def approve_profile(client, profile_id: int, note: str = ""):
    body = {"review_status": "approved", "review_note": note}
    response = client.post(f"/api/v1/profile/{profile_id}/review", json=body)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def approved_profile(app, client, **details):
    result = synthesize_profile(app, client, **details)
    approve_profile(client, result["profile_id"])
    return result


def search(app, client, **body):
    """Run the job search + evaluation task; returns its result."""
    return finish(app, client, client.post("/api/v1/searches", json=body))[1]


def job_ids(client, query: str = "?sort=score&limit=100") -> list[int]:
    return [item["id"] for item in client.get(f"/api/v1/jobs{query}").get_json()["data"]["items"]]


def top_job(client) -> int:
    return job_ids(client)[0]


def generate(app, client, job_id: int, kind: str, *, state: str = "succeeded"):
    return finish(app, client, client.post(f"/api/v1/jobs/{job_id}/documents", json={"kind": kind}), state=state)


def set_application(client, job_id: int, status: str, note: str | None = None):
    body = {"status": status, **({"note": note} if note is not None else {})}
    response = client.patch(f"/api/v1/jobs/{job_id}/application", json=body)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def application_row(client, job_id: int) -> dict:
    return next(card for card in client.get("/api/v1/applications").get_json()["data"] if card["job_id"] == job_id)

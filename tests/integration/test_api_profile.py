import base64
import json

from app import create_app
from core.config import load_settings
from core.db import db_conn
from tests.support import register

PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
    )
).decode()


def _client(app):
    client = register(app, prefix="profile_api")
    return client, client.username


def _run_task(app, client, response):
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["task_id"]
    app.extensions["task_runner"].drain()
    task = client.get(f"/api/v1/tasks/{task_id}").get_json()["data"]
    assert task["state"] == "succeeded", task
    return task_id, client.get(f"/api/v1/tasks/{task_id}/result").get_json()["data"]


def test_session_sign_in_and_out():
    app = create_app()
    client, username = _client(app)
    client.delete("/api/v1/session")
    assert client.get("/api/v1/session").get_json()["data"] == {"user": None}

    wrong = client.post("/api/v1/session", json={"username": username, "password": "wrong-password"})
    assert (wrong.status_code, wrong.get_json()["error_code"]) == (401, 1001)
    signed_in = client.post("/api/v1/session", json={"username": username, "password": "password123"})
    assert signed_in.get_json()["data"]["user"]["username"] == username
    assert client.get("/api/v1/session").get_json()["data"]["user"]["username"] == username
    assert client.get("/api/v1/config").get_json()["data"]["llm_provider"] == "mock"


def test_synthesize_review_edit_and_versions():
    app = create_app()
    client, _ = _client(app)

    task_id, result = _run_task(
        app,
        client,
        client.post(
            "/api/v1/profile/synthesize",
            json={
                "resume_text": "Python SQL Flask AWS",
                "user_details": {"candidate_name": "Profile User", "target_roles": ["Backend Engineer"]},
                "attachments": [{"name": "dot.png", "mime_type": "image/png", "data_base64": PNG_1PX}],
            },
        ),
    )
    with db_conn(load_settings().app.db_path) as conn:
        stored = json.loads(
            conn.execute("SELECT payload_json FROM async_tasks WHERE task_id = ?", (task_id,)).fetchone()[0]
        )
    assert stored["attachments"][0]["name"] == "dot.png"
    assert "data_base64" not in stored["attachments"][0]

    profile_id = result["profile_id"]
    reviewed = client.post(f"/api/v1/profile/{profile_id}/review", json={"review_status": "approved"})
    assert reviewed.get_json()["data"]["review_status"] == "approved"

    master = client.get("/api/v1/profile").get_json()["data"]["profile"]["master_profile"]
    master["profile_summary"] = "Backend engineer focused on reliable APIs."
    edited = client.patch("/api/v1/profile", json={"master_profile": master})
    assert edited.status_code == 201
    edited_profile = edited.get_json()["data"]
    assert (edited_profile["model_name"], edited_profile["review_status"]) == ("user_edit", "approved")
    assert edited_profile["master_profile"]["profile_summary"] == "Backend engineer focused on reliable APIs."

    versions = client.get("/api/v1/profile/versions").get_json()["data"]
    assert [v["profile_version"] for v in versions] == [2, 1]


def test_supplement_creates_a_new_version():
    app = create_app()
    client, _ = _client(app)
    _, created = _run_task(
        app, client, client.post("/api/v1/profile/synthesize", json={"resume_text": "Python SQL Flask"})
    )

    _, supplemented = _run_task(
        app,
        client,
        client.post(
            "/api/v1/profile/supplement",
            json={"selected_fields": ["core_skills"], "answers": {"core_skills": "Go, Kubernetes"}},
        ),
    )

    assert supplemented["profile_version"] == created["profile_version"] + 1


def test_synthesis_input_is_validated():
    client, _ = _client(create_app())

    empty = client.post("/api/v1/profile/synthesize", json={})
    assert (empty.status_code, empty.get_json()["error_code"]) == (400, 2002)
    bad_type = client.post(
        "/api/v1/profile/synthesize",
        json={
            "resume_text": "x",
            "attachments": [{"name": "a.exe", "mime_type": "application/x-msdownload", "data_base64": ""}],
        },
    )
    assert bad_type.status_code == 400
    bad_base64 = client.post(
        "/api/v1/profile/synthesize",
        json={"resume_text": "x", "attachments": [{"name": "a.png", "mime_type": "image/png", "data_base64": "%%%"}]},
    )
    assert bad_base64.status_code == 400


def test_suggested_search_preferences_come_from_the_profile():
    app = create_app()
    client, _ = _client(app)
    _run_task(
        app,
        client,
        client.post(
            "/api/v1/profile/synthesize",
            json={
                "resume_text": "Python SQL",
                "user_details": {
                    "target_roles": ["Data Engineer", "Analytics Engineer"],
                    "preferred_locations": ["Ottawa"],
                },
            },
        ),
    )

    suggested = client.get("/api/v1/search-preferences/suggested").get_json()["data"]

    assert suggested["source"] == "suggested"
    assert suggested["config"]["adzuna"]["keywords"] == ["Data Engineer", "Analytics Engineer"]
    assert suggested["config"]["adzuna"]["location"] == "Ottawa"
    assert client.get("/api/v1/search-preferences").get_json()["data"]["source"] == "default"


def test_suggested_preferences_pick_levels_from_the_years_of_experience_and_sort_by_relevance():
    app = create_app()
    client, _ = _client(app)
    _run_task(
        app,
        client,
        client.post(
            "/api/v1/profile/synthesize",
            json={
                "resume_text": "Python SQL",
                "user_details": {"years_experience": "4", "target_roles": ["Backend Engineer"]},
            },
        ),
    )

    config = client.get("/api/v1/search-preferences/suggested").get_json()["data"]["config"]

    assert config["target_levels"] == ["junior", "mid", "senior"]
    assert config["adzuna"]["sort_by"] == "relevance"


def test_saved_levels_decide_which_searched_jobs_are_kept():
    from tests.support import approved_profile, search

    app = create_app()
    client, _ = _client(app)
    approved_profile(app, client)
    levels = {"adzuna": {"country": "ca", "keywords": ["engineer"]}, "target_levels": ["staff_plus"]}
    assert client.put("/api/v1/search-preferences", json=levels).get_json()["data"]["config"]["target_levels"] == [
        "staff_plus"
    ]

    result = search(app, client)  # the mock jobs are all mid-level titles

    assert (result["inserted_count"], result["skipped_by_level"]) == (0, 4)
    assert client.get("/api/v1/jobs").get_json()["data"]["total"] == 0

    levels["target_levels"] = []
    client.put("/api/v1/search-preferences", json=levels)
    assert search(app, client)["inserted_count"] == 3


def test_sign_up_creates_an_account_and_signs_in():
    client = create_app().test_client()
    response = client.post("/api/v1/account", json={"username": "new_person", "password": "long-enough-1"})
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["user"]["username"] == "new_person"
    assert client.get("/api/v1/session").get_json()["data"]["user"]["username"] == "new_person"

    taken = (
        create_app().test_client().post("/api/v1/account", json={"username": "new_person", "password": "long-enough-2"})
    )
    assert (taken.status_code, taken.get_json()["error_code"]) == (409, 3004)
    short = client.post("/api/v1/account", json={"username": "other", "password": "short"})
    assert (short.status_code, short.get_json()["error_code"]) == (400, 2002)
    reserved = client.post("/api/v1/account", json={"username": "demo", "password": "long-enough-3"})
    assert (reserved.status_code, reserved.get_json()["error_code"]) == (409, 3004)


def test_sign_up_is_refused_while_registration_is_closed(monkeypatch):
    monkeypatch.setenv("REGISTRATION_MODE", "closed")
    response = (
        create_app().test_client().post("/api/v1/account", json={"username": "new_person", "password": "long-enough-1"})
    )
    assert (response.status_code, response.get_json()["error_code"]) == (403, 1003)


def test_sample_resumes_exist_only_in_the_demo():
    app = create_app()
    client = register(app)
    refused = client.post("/api/v1/profile/synthesize", json={"sample": "pdf"})
    assert (refused.status_code, refused.get_json()["error_code"]) == (400, 2002)
    assert client.get("/api/v1/demo/sample-resumes/pdf").status_code == 404

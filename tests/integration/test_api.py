"""Product flows through `/api/v1`: pipeline, owner scoping, profile gates, search settings, documents."""

import os

from app import create_app
from core.config import load_settings, reset_config
from core.db import db_conn
from core.search_preferences import get_effective_search_config
from tests.conftest import patch_llm_settings
from tests.support import (
    application_row,
    approve_profile,
    approved_profile,
    finish,
    generate,
    register,
    search,
    set_application,
    synthesize_profile,
    top_job,
)


def _profile(client):
    return client.get("/api/v1/profile").get_json()["data"]["profile"]


def _readiness(client):
    return client.get("/api/v1/overview").get_json()["data"]["readiness"]


def test_search_generate_and_track_an_application():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    job_id = top_job(client)
    _, letter = generate(app, client, job_id, "cover_letter")
    assert (letter["job_id"], letter["version"]) == (job_id, 1)

    updated = set_application(client, job_id, "submitted", "manual apply done")
    assert updated["status"] == "submitted"
    assert any(card["job_id"] == job_id for card in client.get("/api/v1/applications").get_json()["data"])


def test_application_status_accepts_extended_user_states():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    job_id = top_job(client)

    for status in ["offer", "hired", "withdrawn"]:
        assert set_application(client, job_id, status, f"tracking state: {status}")["status"] == status

    row = application_row(client, job_id)
    assert (row["status"], row["note"]) == ("withdrawn", "tracking state: withdrawn")


def test_multi_user_owner_scoping_for_jobs_tasks_applications_and_documents():
    app = create_app()
    client_a = register(app)
    client_b = register(app)
    for client in (client_a, client_b):
        approved_profile(app, client)
        search(app, client)
    job_a = top_job(client_a)
    job_b = top_job(client_b)
    assert job_a != job_b

    assert client_b.patch(f"/api/v1/jobs/{job_a}/application", json={"status": "submitted"}).status_code == 404
    set_application(client_a, job_a, "submitted", "owner update")
    assert any(card["job_id"] == job_a for card in client_a.get("/api/v1/applications").get_json()["data"])
    assert all(card["job_id"] != job_a for card in client_b.get("/api/v1/applications").get_json()["data"])
    assert client_b.get(f"/api/v1/jobs/{job_a}").status_code == 404
    assert client_b.post(f"/api/v1/jobs/{job_a}/documents", json={"kind": "resume"}).status_code == 404

    started = client_a.post(
        "/api/v1/jobs/manual",
        json={"title": "Scoped Backend Engineer", "description": "Build Python APIs and SQL services."},
    )
    task_id = started.get_json()["data"]["task_id"]
    assert client_b.get(f"/api/v1/tasks/{task_id}").status_code == 404
    app.extensions["task_runner"].drain()
    assert job_b not in {item["id"] for item in client_a.get("/api/v1/jobs").get_json()["data"]["items"]}


def test_cover_letter_generation_marks_the_application_ready():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    job_id = top_job(client)

    generate(app, client, job_id, "cover_letter")

    assert application_row(client, job_id)["status"] == "ready"


def test_profile_synthesize_json_input():
    app = create_app()
    client = register(app)

    result = synthesize_profile(
        app,
        client,
        resume_text="Python Flask SQL backend engineer",
        candidate_name="Alex Chen",
        current_title="Backend Engineer",
        location="Toronto",
        years_experience="5",
        target_roles=["Senior Backend Engineer"],
        preferred_locations=["Toronto", "Remote - Canada"],
    )
    assert result["profile_id"] >= 1 and result["profile_version"] >= 1

    profile = _profile(client)["master_profile"]
    assert profile["identity"]["name"] == "Alex Chen"
    assert len(profile["core_skills"]) >= 1
    assert isinstance(profile["missing_information"], list)
    assert isinstance(profile["completeness_score"], int)


def test_profile_synthesize_accepts_structured_details_without_resume_text():
    app = create_app()
    client = register(app)

    finish(
        app,
        client,
        client.post(
            "/api/v1/profile/synthesize",
            json={
                "user_details": {
                    "candidate_name": "Morgan Li",
                    "current_title": "Data Engineer",
                    "location": "Vancouver",
                    "years_experience": "4",
                    "target_roles": ["Data Engineer", "ML Engineer"],
                    "preferred_locations": ["Vancouver", "Remote"],
                    "work_authorization": "Canada PR",
                    "key_skills": "Python, Spark, Airflow",
                }
            },
        ),
    )

    profile = _profile(client)["master_profile"]
    assert profile["identity"]["name"] == "Morgan Li"
    assert profile["preferences"]["target_roles"] == ["Data Engineer", "ML Engineer"]
    assert profile["preferences"]["work_authorization"] == "Canada PR"


def test_profile_supplement_creates_new_profile_version_from_selected_fields():
    app = create_app()
    client = register(app)
    initial = finish(
        app,
        client,
        client.post(
            "/api/v1/profile/synthesize",
            json={
                "resume_text": "Backend engineer experienced in distributed services and APIs.",
                "extra_context": "Built internal platforms and improved deployment speed.",
            },
        ),
    )[1]

    _, supplemented = finish(
        app,
        client,
        client.post(
            "/api/v1/profile/supplement",
            json={
                "profile_id": initial["profile_id"],
                "selected_fields": ["identity.name", "preferences.target_roles"],
                "answers": {
                    "identity.name": "Taylor Wong",
                    "preferences.target_roles": "Senior Backend Engineer, Platform Engineer",
                },
                "additional_context": "Led migration that reduced deployment time by 40%.",
            },
        ),
    )

    assert supplemented["profile_version"] > initial["profile_version"]
    profile = _profile(client)["master_profile"]
    assert profile["identity"]["name"] == "Taylor Wong"
    assert "Senior Backend Engineer" in profile["preferences"]["target_roles"]


def test_profile_review_gate_requires_latest_approved_version():
    app = create_app()
    client = register(app)
    initial = synthesize_profile(app, client)

    pending = _readiness(client)
    assert pending["allowed"] is False
    assert pending["review_status"] == "pending"

    approve_profile(client, initial["profile_id"], "Looks accurate.")
    approved = _readiness(client)
    assert approved["allowed"] is True
    assert approved["review_status"] == "approved"

    _, latest = finish(
        app,
        client,
        client.post(
            "/api/v1/profile/supplement",
            json={
                "profile_id": initial["profile_id"],
                "selected_fields": ["profile_summary"],
                "answers": {"profile_summary": "Emphasize backend API delivery and cloud operations."},
                "additional_context": "Profile review correction: focus on backend systems.",
            },
        ),
    )
    assert latest["profile_id"] != initial["profile_id"]
    reset = _readiness(client)
    assert (reset["allowed"], reset["profile_id"], reset["review_status"]) == (False, latest["profile_id"], "pending")

    approve_profile(client, initial["profile_id"])  # approving an old version never unlocks the newest one
    still_blocked = _readiness(client)
    assert (still_blocked["allowed"], still_blocked["profile_id"]) == (False, latest["profile_id"])

    approve_profile(client, latest["profile_id"])
    assert _readiness(client)["allowed"] is True


def test_search_preferences_are_saved_per_account(tmp_path):
    previous_search_file = os.environ.get("SEARCH_PARAMS_FILE")
    search_file = tmp_path / "search_params.yaml"
    os.environ["SEARCH_PARAMS_FILE"] = str(search_file)
    reset_config()

    try:
        app = create_app()
        client = register(app, "prefs_owner")

        resp = client.put(
            "/api/v1/search-preferences",
            json={
                "adzuna": {
                    "country": "ca",
                    "location": "toronto",
                    "keywords": ["backend engineer", "python developer"],
                    "results_per_page": 10,
                    "max_pages": 1,
                    "days_old": 7,
                    "sort_by": "date",
                    "salary_min": 100000,
                    "salary_max": 180000,
                    "distance": 20,
                    "company": "Shopify",
                    "category": "it-jobs",
                    "full_time": True,
                    "part_time": False,
                    "permanent": True,
                    "contract": False,
                    "what_phrase": "machine learning",
                    "what_and": "python flask",
                    "what_or": "backend api",
                    "what_exclude": "senior",
                }
            },
        )
        assert resp.status_code == 200

        with db_conn(load_settings().app.db_path) as conn:
            user_id = conn.execute("SELECT id FROM users WHERE username = 'prefs_owner'").fetchone()["id"]
            cfg = get_effective_search_config(conn, int(user_id))[0].adzuna
        assert cfg.location == "toronto"
        assert cfg.keywords == ["backend engineer", "python developer"]
        assert cfg.results_per_page == 10
        assert cfg.max_pages == 1
        assert cfg.days_old == 7
        assert (cfg.salary_min, cfg.salary_max, cfg.distance) == (100000, 180000, 20)
        assert (cfg.company, cfg.category) == ("Shopify", "it-jobs")
        assert (cfg.full_time, cfg.part_time, cfg.permanent, cfg.contract) == (True, False, True, False)
        assert (cfg.what_phrase, cfg.what_and, cfg.what_or, cfg.what_exclude) == (
            "machine learning",
            "python flask",
            "backend api",
            "senior",
        )
        assert not search_file.exists()
    finally:
        if previous_search_file is None:
            os.environ.pop("SEARCH_PARAMS_FILE", None)
        else:
            os.environ["SEARCH_PARAMS_FILE"] = previous_search_file
        reset_config()


def test_user_search_params_are_owner_scoped():
    app = create_app()
    client_a = register(app, "search_owner_a")
    client_b = register(app, "search_owner_b")

    resp_a = client_a.put(
        "/api/v1/search-preferences",
        json={"adzuna": {"country": "ca", "location": "toronto", "keywords": ["backend engineer"], "days_old": 5}},
    )
    resp_b = client_b.put(
        "/api/v1/search-preferences",
        json={
            "adzuna": {
                "country": "us",
                "location": "seattle",
                "keywords": ["platform engineer"],
                "days_old": 10,
                "sort_by": "relevance",
            }
        },
    )
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    with db_conn(load_settings().app.db_path) as conn:
        user_a = conn.execute("SELECT id FROM users WHERE username = ?", ("search_owner_a",)).fetchone()
        user_b = conn.execute("SELECT id FROM users WHERE username = ?", ("search_owner_b",)).fetchone()
        cfg_a, source_a = get_effective_search_config(conn, int(user_a["id"]))
        cfg_b, source_b = get_effective_search_config(conn, int(user_b["id"]))

    assert source_a == "user"
    assert source_b == "user"
    assert cfg_a.adzuna.location == "toronto"
    assert cfg_a.adzuna.keywords == ["backend engineer"]
    assert cfg_b.adzuna.location == "seattle"
    assert cfg_b.adzuna.keywords == ["platform engineer"]


def test_generation_records_the_decision_and_the_job_page_shows_the_resume():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    job_id = top_job(client)

    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    assert detail["decision"] is None or detail["decision"]["generate_resume"] is False
    assert detail["documents"]["resume"] is None

    _, resume = generate(app, client, job_id, "resume")
    assert (resume["job_id"], resume["version"]) == (job_id, 1)

    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    assert detail["decision"]["generate_resume"] is True and detail["decision"]["viewed_match_at"]
    assert {"dimension_scores", "recommendation_level", "risk_flags"} <= set(detail["match"])
    assert detail["documents"]["resume"]["version"] == 1


def test_fullstack_enabled_generates_llm_documents_and_records_profile_metadata(monkeypatch):
    patch_llm_settings(monkeypatch, fullstack_enabled=True)
    app = create_app()
    client = register(app)
    profile = approved_profile(app, client, resume_text="Python Flask TypeScript engineer")
    search(app, client)
    job_id = top_job(client)

    for kind in ("resume", "cover_letter"):
        generate(app, client, job_id, kind)

    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    assert detail["match"]["source_profile_id"] == profile["profile_id"]
    for kind in ("resume", "cover_letter"):
        document = client.get(f"/api/v1/documents/{kind}/{detail['documents'][kind]['id']}").get_json()["data"]
        assert document["evidence_map"]["mode"] == "llm"
        assert document["source_profile_id"] == profile["profile_id"]


def test_readiness_reports_the_gate():
    app = create_app()
    client = register(app)
    assert _readiness(client)["allowed"] is False

    approved_profile(app, client)

    assert _readiness(client)["allowed"] is True


def test_re_evaluate_requires_ready_profile_and_tracks_profile_version():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)

    synthesize_profile(app, client)  # a newer version that nobody has approved yet
    blocked, _ = finish(app, client, client.post("/api/v1/evaluations/rerun", json={"scope": "all"}), state="failed")
    assert "profile" in blocked["error_message_safe"].lower()

    newest = _profile(client)
    approve_profile(client, newest["id"])
    _, rerun = finish(app, client, client.post("/api/v1/evaluations/rerun", json={"scope": "all"}))
    assert rerun["evaluated_count"] >= 1
    assert rerun["source_profile_version"] == newest["profile_version"]

    match = client.get(f"/api/v1/jobs/{top_job(client)}").get_json()["data"]["match"]
    assert match["source_profile_version"] == newest["profile_version"]

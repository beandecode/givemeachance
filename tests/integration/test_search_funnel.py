"""Search filters, the relevance order and swipe reasons with their suggestions (ADR-017)."""

from core.config import load_settings
from core.db import db_conn
from core.ingest import _description_hash
from core.repositories.jobs import insert_job_if_new
from core.schemas import JobRecord
from core.suggestions_service import search_suggestions
from tests.support import approved_profile, register, search


def _app():
    from app import create_app

    return create_app()


def _client(app):
    client = register(app, prefix="funnel")
    approved_profile(app, client, candidate_name="Funnel User")
    return client


def _config(client, **changes):
    config = client.get("/api/v1/search-preferences").get_json()["data"]["config"]
    config.update(changes)
    response = client.put("/api/v1/search-preferences", json=config)
    assert response.status_code == 200, response.get_json()


def test_title_filter_skips_postings_and_the_search_says_how_many():
    app = _app()
    client = _client(app)
    _config(client, exclude_title_words=["Developer"])

    result = search(app, client)

    assert result["skipped_by_filters"]["title_word"] >= 1  # the mock board has "... Developer" titles
    assert result["skipped_by_filters"]["salary"] == result["skipped_by_filters"]["work_mode"] == 0
    titles = [j["title"] for j in client.get("/api/v1/jobs?limit=100").get_json()["data"]["items"]]
    assert titles and not any("Developer" in title for title in titles)


def test_searched_jobs_get_a_relevance_and_the_best_are_scored_first():
    app = _app()
    client = _client(app)

    result = search(app, client, score_limit=1)

    items = client.get("/api/v1/jobs?limit=100").get_json()["data"]["items"]
    assert all(isinstance(item["relevance"], int) and 0 <= item["relevance"] <= 100 for item in items)
    scored = [item for item in items if item["match_score"] is not None]
    unscored = [item for item in items if item["match_score"] is None]
    assert result["not_scored_by_choice"] == len(unscored) >= 1 and len(scored) == 1
    assert all(scored[0]["relevance"] >= item["relevance"] for item in unscored)


def test_a_skip_reason_is_stored_only_for_skips():
    app = _app()
    client = _client(app)
    search(app, client)
    job_id = client.get("/api/v1/jobs?limit=1").get_json()["data"]["items"][0]["id"]

    assert client.put(f"/api/v1/jobs/{job_id}/triage", json={"action": "skipped", "reason": "pay"}).status_code == 200
    with db_conn(load_settings().app.db_path) as conn:
        assert conn.execute("SELECT reason FROM job_triage WHERE job_id = ?", (job_id,)).fetchone()["reason"] == "pay"

    assert (
        client.put(f"/api/v1/jobs/{job_id}/triage", json={"action": "waitlisted", "reason": "pay"}).status_code == 200
    )
    with db_conn(load_settings().app.db_path) as conn:
        assert conn.execute("SELECT reason FROM job_triage WHERE job_id = ?", (job_id,)).fetchone()["reason"] is None
    assert client.put(f"/api/v1/jobs/{job_id}/triage", json={"action": "skipped", "reason": "bogus"}).status_code == 400


def _skipped(conn, user_id, titles, reason):
    for index, title in enumerate(titles):
        job = JobRecord.model_validate(
            {
                "id": f"s{index}-{title}",
                "title": title,
                "company": f"Co{index}",
                "location": "x",
                "description": f"unique text {index} {title}",
                "posted_date": "2026-10-01",
                "source": "adzuna",
                "url": "u",
            }
        )
        job_id = insert_job_if_new(conn, job, _description_hash(job), "{}", owner_user_id=user_id)
        conn.execute(
            "INSERT INTO job_triage (user_id, job_id, action, reason, decided_at) VALUES (?, ?, 'skipped', ?, 'now')",
            (user_id, job_id, reason),
        )


def test_repeated_reasons_become_suggestions_and_a_single_skip_does_not():
    app = _app()
    client = _client(app)
    _config(client, target_levels=["mid", "senior"])
    user_id = client.get("/api/v1/session").get_json()["data"]["user"]["id"]
    with db_conn(load_settings().app.db_path) as conn:
        _skipped(conn, user_id, ["Engineer A", "Engineer B"], "too_senior")
        assert search_suggestions(conn, user_id) == []
        _skipped(conn, user_id, ["Engineer C"], "too_senior")
        _skipped(conn, user_id, ["Marketing Lead", "Marketing Analyst", "Marketing Manager"], "wrong_field")

    suggestions = client.get("/api/v1/search-suggestions").get_json()["data"]
    assert {"kind": "remove_level", "value": "senior", "count": 3} in suggestions
    assert {"kind": "exclude_word", "value": "marketing", "count": 3} in suggestions


def test_calibration_groups_scores_by_what_the_user_did():
    from core.calibration import calibration_report

    app = _app()
    client = _client(app)
    search(app, client)
    jobs = client.get("/api/v1/jobs?sort=score&limit=100").get_json()["data"]["items"]
    assert len(jobs) >= 2
    client.put(f"/api/v1/jobs/{jobs[0]['id']}/triage", json={"action": "waitlisted"})
    client.patch(f"/api/v1/jobs/{jobs[1]['id']}/application", json={"status": "submitted"})
    user_id = client.get("/api/v1/session").get_json()["data"]["user"]["id"]

    with db_conn(load_settings().app.db_path) as conn:
        rows = {row["outcome"]: row for row in calibration_report(conn, user_id)}

    assert rows["waitlisted"]["count"] == 1 and rows["submitted"]["count"] == 1
    assert rows["waitlisted"]["lowest"] == rows["waitlisted"]["highest"] == jobs[0]["match_score"]

"""Search options: fetch limit, scoring limit, honest results, quota stop and the one-search-at-a-time guard."""

from adapters.llm.gemini_api import ProviderQuotaExhausted
from adapters.llm.mock_gemini import MockGeminiEvaluator
from app import create_app
from core.config import load_settings
from tests.support import approved_profile, finish, register


def _client(app, username=None):
    client = register(app, username, prefix="search_opts")
    approved_profile(app, client, candidate_name="Search User")
    return client


def _search(app, client, body=None):
    return finish(app, client, client.post("/api/v1/searches", json=body or {}))[1]


def _scored(client):
    items = client.get("/api/v1/jobs?limit=100").get_json()["data"]["items"]
    return [job["match_score"] for job in items if job["match_score"] is not None], len(items)


def test_default_search_scores_every_new_job_and_reports_it():
    app = create_app()
    client = _client(app)
    result = _search(app, client)

    assert result["inserted_count"] >= 2
    assert result["evaluated_count"] == result["inserted_count"]
    assert result["not_scored_count"] == 0 and result["quota_exhausted"] is False
    assert result["score_limit"] is None and result["fetch_limit"] == load_settings().pipeline.daily_limit
    assert result["source_stats"] and result["source_stats"][0]["status"] == "success"


def test_fetch_limit_counts_new_jobs_only_so_duplicates_do_not_use_it_up():
    app = create_app()
    client = _client(app)

    first = _search(app, client, {"fetch_limit": 1, "score_limit": 0})
    second = _search(app, client, {"fetch_limit": 1, "score_limit": 0})

    assert first["inserted_count"] == 1 and first["fetch_limit"] == 1
    assert second["inserted_count"] == 1
    assert second["duplicates_skipped"] >= 1
    scored, total = _scored(client)
    assert total == 2 and scored == []


def test_fetch_limit_above_the_server_cap_is_capped():
    app = create_app()
    client = _client(app)
    result = _search(app, client, {"fetch_limit": 500})
    assert result["fetch_limit"] == load_settings().pipeline.daily_limit


def test_fetch_only_never_calls_the_scoring_provider(monkeypatch):
    app = create_app()
    client = _client(app)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("scoring must not run for score_limit 0")

    monkeypatch.setattr(MockGeminiEvaluator, "evaluate", forbidden)
    result = _search(app, client, {"score_limit": 0})

    assert result["evaluated_count"] == 0
    assert result["not_scored_by_choice"] == result["inserted_count"] == result["not_scored_count"]


def test_score_limit_scores_only_the_first_jobs():
    app = create_app()
    client = _client(app)
    result = _search(app, client, {"score_limit": 1})

    assert result["inserted_count"] >= 2 and result["evaluated_count"] == 1
    assert result["not_scored_by_choice"] == result["inserted_count"] - 1
    scored, total = _scored(client)
    assert len(scored) == 1 and total == result["inserted_count"]


def test_quota_running_out_stops_scoring_and_is_reported(monkeypatch):
    app = create_app()
    client = _client(app)
    original = MockGeminiEvaluator.evaluate
    calls = []

    def evaluate(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise ProviderQuotaExhausted("Gemini daily quota reached: 40/40")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(MockGeminiEvaluator, "evaluate", evaluate)
    task, result = finish(app, client, client.post("/api/v1/searches", json={}))

    assert task["state"] == "succeeded"
    assert len(calls) == 2  # the third job was never tried
    assert result["evaluated_count"] == 1 and result["quota_exhausted"] is True
    assert result["not_scored_by_quota"] == result["inserted_count"] - 1
    assert result["not_scored_count"] == result["inserted_count"] - 1


def test_only_one_search_runs_at_a_time_per_user():
    app = create_app()
    client = _client(app)
    runner = app.extensions["task_runner"]
    original_enqueue = runner.enqueue
    runner.enqueue = lambda task_id, handler: None  # the first search stays queued
    try:
        first = client.post("/api/v1/searches", json={})
        same = client.post("/api/v1/searches", json={})
        different = client.post("/api/v1/searches", json={"fetch_limit": 1})
    finally:
        runner.enqueue = original_enqueue

    assert first.status_code == 202
    assert same.get_json()["data"]["task_id"] == first.get_json()["data"]["task_id"]
    assert different.status_code == 409
    assert different.get_json()["error_code"] == 3004
    assert "already running" in different.get_json()["message"]


def test_config_reports_the_real_per_run_cap():
    app = create_app()
    client = _client(app)
    data = client.get("/api/v1/config").get_json()["data"]
    assert data["search_results_per_run"] == load_settings().pipeline.daily_limit

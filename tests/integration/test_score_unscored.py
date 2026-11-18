"""Scoring jobs that have no score yet: explicit job ids, the `unscored` scope and the `scored` list filter."""

from adapters.llm.gemini_api import ProviderQuotaExhausted
from adapters.llm.mock_gemini import MockGeminiEvaluator
from app import create_app
from tests.support import approved_profile, finish, register


def _fetched_unscored(prefix="unscored"):
    """A user with an approved profile and three jobs that were fetched but not scored."""
    app = create_app()
    client = register(app, prefix=prefix)
    approved_profile(app, client)
    finish(app, client, client.post("/api/v1/searches", json={"score_limit": 0}))
    return app, client


def _jobs(client, query=""):
    return client.get(f"/api/v1/jobs?limit=100{query}").get_json()["data"]


def _rerun(app, client, body):
    return finish(app, client, client.post("/api/v1/evaluations/rerun", json=body))[1]


def test_scoring_one_unscored_job_by_id_creates_its_first_score():
    app, client = _fetched_unscored()
    job_id = _jobs(client)["items"][0]["id"]
    assert _jobs(client, "&scored=true")["total"] == 0

    result = _rerun(app, client, {"job_ids": [job_id]})

    assert result["target_job_count"] == 1 and result["evaluated_count"] == 1
    scored = _jobs(client, "&scored=true")
    assert [job["id"] for job in scored["items"]] == [job_id]
    assert scored["items"][0]["match_score"] is not None


def test_unscored_scope_scores_only_jobs_without_a_score_newest_first_up_to_the_limit():
    app, client = _fetched_unscored()
    total = _jobs(client)["total"]
    assert total >= 3

    first = _rerun(app, client, {"scope": "unscored", "limit": 1})
    assert first["target_job_count"] == 1 and first["evaluated_count"] == 1
    assert _jobs(client, "&scored=false")["total"] == total - 1

    rest = _rerun(app, client, {"scope": "unscored"})
    assert rest["target_job_count"] == total - 1
    assert _jobs(client, "&scored=false")["total"] == 0
    assert _jobs(client, "&scored=true")["total"] == total

    nothing = _rerun(app, client, {"scope": "unscored"})
    assert nothing["target_job_count"] == 0 and nothing["evaluated_count"] == 0


def test_unscored_scope_skips_archived_jobs():
    app, client = _fetched_unscored()
    archived_id = _jobs(client)["items"][0]["id"]
    assert client.post(f"/api/v1/jobs/{archived_id}/archive").status_code == 200

    _rerun(app, client, {"scope": "unscored"})

    unscored = client.get("/api/v1/jobs?include_archived=true&scored=false").get_json()["data"]["items"]
    assert [job["id"] for job in unscored] == [archived_id]


def test_nobody_can_score_another_users_jobs():
    app, owner = _fetched_unscored("unscored_owner")
    job_id = _jobs(owner)["items"][0]["id"]
    stranger = register(app, prefix="unscored_stranger")
    approved_profile(app, stranger)

    by_id = _rerun(app, stranger, {"job_ids": [job_id]})
    by_scope = _rerun(app, stranger, {"scope": "unscored"})

    assert by_id["target_job_count"] == 0 and by_scope["target_job_count"] == 0
    assert _jobs(owner, "&scored=true")["total"] == 0


def test_scoring_stops_when_the_daily_quota_runs_out(monkeypatch):
    app, client = _fetched_unscored()
    total = _jobs(client)["total"]
    original = MockGeminiEvaluator.evaluate
    calls = []

    def evaluate(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise ProviderQuotaExhausted("Gemini daily quota reached: 40/40")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(MockGeminiEvaluator, "evaluate", evaluate)
    task, result = finish(app, client, client.post("/api/v1/evaluations/rerun", json={"scope": "unscored"}))

    assert task["state"] == "succeeded" and len(calls) == 2
    assert result["evaluated_count"] == 1 and result["quota_exhausted"] is True
    assert result["not_attempted_count"] == total - 1
    assert _jobs(client, "&scored=false")["total"] == total - 1

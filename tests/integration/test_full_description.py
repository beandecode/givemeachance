"""A job known only from the job board's preview is scored from its full text, or not at all."""

from __future__ import annotations

import pytest

import core.evaluate as evaluate
from app import create_app
from core.config import load_settings
from core.db import db_conn
from tests.support import approved_profile, finish, job_ids, register, search

PREVIEW = "Build data pipelines and models in Python. " * 10 + "…"
FULL = "Build data pipelines and models in Python and SQL. You need 2+ years of experience. " * 20


@pytest.fixture
def app():
    return create_app()


def _make_preview(job_id: int) -> None:
    with db_conn(load_settings().app.db_path) as conn:
        conn.execute(
            "UPDATE jobs SET source = 'adzuna', description = ?, url = ? WHERE id = ?",
            (PREVIEW, f"https://www.adzuna.ca/details/{job_id}", job_id),
        )
        conn.execute("DELETE FROM evaluations WHERE job_id = ?", (job_id,))


def _rescore(app, client, job_id: int) -> dict:
    response = client.post("/api/v1/evaluations/rerun", json={"scope": "all", "job_ids": [job_id]})
    return finish(app, client, response)[1]


def test_a_preview_is_replaced_by_the_full_text_before_scoring(app, monkeypatch):
    client = register(app)
    approved_profile(app, client)
    search(app, client, score_limit=0)
    job_id = job_ids(client)[0]
    _make_preview(job_id)
    fetched: list[str] = []

    def fake_fetch(url, preview="", **_):
        fetched.append(url)
        return FULL

    monkeypatch.setattr(evaluate, "fetch_full_description", fake_fetch)
    result = _rescore(app, client, job_id)

    assert fetched == [f"https://www.adzuna.ca/details/{job_id}"]
    assert result["evaluated_count"] == 1 and result["needs_description_count"] == 0
    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    assert detail["description"] == FULL and detail["description_is_snippet"] is False
    assert detail["match"] is not None


def test_a_preview_without_full_text_is_left_unscored(app, monkeypatch):
    client = register(app)
    approved_profile(app, client)
    search(app, client, score_limit=0)
    job_id = job_ids(client)[0]
    _make_preview(job_id)
    monkeypatch.setattr(evaluate, "fetch_full_description", lambda url, preview="", **_: None)

    result = _rescore(app, client, job_id)

    assert result["evaluated_count"] == 0 and result["needs_description_count"] == 1
    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    assert detail["match"] is None and detail["description_is_snippet"] is True

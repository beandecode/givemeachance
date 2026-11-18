"""Generation runs the LLM call without holding the SQLite writer lock (roadmap Phase 1b).

That allows concurrent writes during the call, so the results must be written in a fresh
transaction that re-checks the inputs and allocates the version number.
"""

import threading

import pytest

from adapters.llm.mock_gemini import MockGeminiEvaluator
from app import create_app
from core.config import load_settings
from core.db import db_conn
from core.generation_service import _ResumeGenerationError, _run_resume_generation
from core.repositories.decisions import mark_match_viewed, upsert_generation_decision
from tests.support import approved_profile, register, search, top_job


def _job_ready_for_resume_generation():
    app = create_app()
    client = register(app, prefix="short_tx")
    approved_profile(app, client)
    search(app, client)
    job_id = top_job(client)
    with db_conn(load_settings().app.db_path) as conn:
        mark_match_viewed(conn, job_id, decided_by="test")
        upsert_generation_decision(
            conn, job_id=job_id, generate_resume=True, generate_cover_letter=None, decided_by="test"
        )
        user = conn.execute("SELECT * FROM users WHERE username = ?", (client.username,)).fetchone()
    return job_id, user


def _generate_resume(job_id, user):
    settings = load_settings()
    with db_conn(settings.app.db_path) as conn:
        return _run_resume_generation(
            conn,
            settings,
            job_id=job_id,
            profile_id_raw=None,
            style="ats",
            decided_by="test",
            current_user=user,
        )


def _wrap_rewrite_resume(monkeypatch, before_return):
    original = MockGeminiEvaluator.rewrite_resume

    def wrapped(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        before_return()
        return result

    monkeypatch.setattr(MockGeminiEvaluator, "rewrite_resume", wrapped)


def test_concurrent_generations_get_distinct_versions(monkeypatch):
    job_id, user = _job_ready_for_resume_generation()
    both_inside_llm_call = threading.Barrier(2, timeout=10)
    _wrap_rewrite_resume(monkeypatch, both_inside_llm_call.wait)

    results: list[dict] = []
    errors: list[BaseException] = []

    def worker():
        try:
            results.append(_generate_resume(job_id, user))
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(result["version"] for result in results) == [1, 2]


def test_report_changed_during_generation_is_rejected_and_nothing_is_saved(monkeypatch):
    job_id, user = _job_ready_for_resume_generation()
    db_path = load_settings().app.db_path

    def re_evaluate_meanwhile():
        with db_conn(db_path) as other:
            other.execute(
                "UPDATE evaluations SET created_at = '2099-01-01T00:00:00+00:00' WHERE job_id = ?",
                (job_id,),
            )

    _wrap_rewrite_resume(monkeypatch, re_evaluate_meanwhile)

    with pytest.raises(_ResumeGenerationError) as excinfo:
        _generate_resume(job_id, user)

    assert excinfo.value.status_code == 409
    with db_conn(db_path) as conn:
        saved = conn.execute("SELECT COUNT(*) FROM generated_resumes WHERE job_id = ?", (job_id,)).fetchone()[0]
    assert saved == 0


def test_resume_generation_marks_application_materials_ready():
    job_id, user = _job_ready_for_resume_generation()

    _generate_resume(job_id, user)

    with db_conn(load_settings().app.db_path) as conn:
        row = conn.execute("SELECT status, status_note FROM applications WHERE job_id = ?", (job_id,)).fetchone()
    assert (row["status"], row["status_note"]) == ("ready", "resume generated")

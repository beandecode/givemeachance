"""Generated documents are checked; one retry fixes serious problems and what remains is shown as a warning."""

import json
from pathlib import Path

from adapters.llm.mock_gemini import MockGeminiEvaluator
from app import create_app
from tests.support import approved_profile, generate, register, search, top_job

GOOD = "# Casey Chen\n\n## Skills\n- Python, SQL, Flask\n"
ROOT = Path(__file__).resolve().parents[2]
BAD = "# Casey Chen\n\n## Skills\n- Python, [Skill], unknown\n"


def _ready_job():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    return app, client, top_job(client)


def _document(client, job_id, kind="resume"):
    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    return client.get(f"/api/v1/documents/{kind}/{detail['documents'][kind]['id']}").get_json()["data"]


def _script(monkeypatch, *drafts):
    calls = []

    def rewrite(self, master_profile, job, match_report, style="ats", fixes=None):
        calls.append(fixes)
        return {"content_md": drafts[min(len(calls), len(drafts)) - 1], "evidence_notes": [], "model_name": "m"}

    monkeypatch.setattr(MockGeminiEvaluator, "rewrite_resume", rewrite)
    return calls


def test_a_clean_first_draft_is_saved_without_a_retry_or_warning(monkeypatch):
    calls = _script(monkeypatch, GOOD)
    app, client, job_id = _ready_job()

    generate(app, client, job_id, "resume")

    document = _document(client, job_id)
    assert calls == [None]
    assert document["content_md"] == GOOD
    assert "warnings" not in document["evidence_map"] and "retried" not in document["evidence_map"]


def test_a_placeholder_gets_one_retry_with_the_problems_listed(monkeypatch):
    calls = _script(monkeypatch, BAD, GOOD)
    app, client, job_id = _ready_job()

    generate(app, client, job_id, "resume")

    document = _document(client, job_id)
    assert calls[0] is None and calls[1] and any("placeholder" in fix for fix in calls[1])
    assert document["content_md"] == GOOD
    assert document["evidence_map"]["retried"] is True and "warnings" not in document["evidence_map"]


def test_problems_that_survive_the_retry_are_kept_as_warnings(monkeypatch):
    calls = _script(monkeypatch, BAD, BAD)
    app, client, job_id = _ready_job()

    generate(app, client, job_id, "resume")

    document = _document(client, job_id)
    assert len(calls) == 2  # exactly one retry, never a loop
    assert document["content_md"] == BAD
    assert document["evidence_map"]["warnings"]
    assert all("placeholder" in warning or "unknown" in warning for warning in document["evidence_map"]["warnings"])


def test_the_mock_provider_passes_its_own_checks_on_a_complete_profile():
    app = create_app()
    client = register(app)
    profile = json.loads((ROOT / "data/mock/demo_profile.json").read_text())
    assert client.patch("/api/v1/profile", json={"master_profile": profile}).status_code == 201
    search(app, client)
    job_id = top_job(client)

    generate(app, client, job_id, "resume")
    generate(app, client, job_id, "cover_letter")

    for kind in ("resume", "cover_letter"):
        evidence = _document(client, job_id, kind)["evidence_map"]
        assert "warnings" not in evidence, evidence

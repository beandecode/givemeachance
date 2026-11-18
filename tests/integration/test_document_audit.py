"""The fact check: claims in a generated document are linked to the profile; unsupported ones get one rewrite."""

from adapters.llm.mock_gemini import MockGeminiEvaluator
from app import create_app
from core.errors import UserFacingError
from tests.conftest import patch_llm_settings
from tests.support import approved_profile, generate, register, search, top_job

CLEAN = "# Casey Chen\n\n## Skills\n- Python, SQL\n"
INVENTED = "# Casey Chen\n\n## Skills\n- Python, SQL\n- Ran a 50-person team at Globex\n"


def _ready_job():
    app = create_app()
    client = register(app)
    approved_profile(app, client)
    search(app, client)
    return app, client, top_job(client)


def _document(client, job_id):
    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    return client.get(f"/api/v1/documents/resume/{detail['documents']['resume']['id']}").get_json()["data"]


def _scripted(monkeypatch, drafts, audits):
    """`drafts` and `audits` are consumed in order (the last one repeats); returns the recorded calls."""
    calls = {"rewrite": [], "audit": []}

    def rewrite(self, master_profile, job, match_report, style="ats", fixes=None):
        calls["rewrite"].append(fixes)
        return {
            "content_md": drafts[min(len(calls["rewrite"]), len(drafts)) - 1],
            "evidence_notes": [],
            "model_name": "m",
        }

    def audit(self, master_profile, content_md, kind):
        calls["audit"].append(content_md)
        result = audits[min(len(calls["audit"]), len(audits)) - 1]
        if isinstance(result, Exception):
            raise result
        return {"claims": result, "model_name": "auditor"}

    monkeypatch.setattr(MockGeminiEvaluator, "rewrite_resume", rewrite)
    monkeypatch.setattr(MockGeminiEvaluator, "audit_document", audit)
    return calls


def _claim(text, status):
    return {"text": text, "status": status, "profile_path": "", "quote": ""}


GOOD_CLAIMS = [_claim("Python", "supported")]
BAD_CLAIMS = [_claim("Python", "supported"), _claim("Ran a 50-person team at Globex", "unsupported")]


def test_a_clean_audit_stores_the_claims_without_a_retry(monkeypatch):
    calls = _scripted(monkeypatch, [CLEAN], [GOOD_CLAIMS])
    app, client, job_id = _ready_job()

    generate(app, client, job_id, "resume")

    evidence = _document(client, job_id)["evidence_map"]
    assert len(calls["rewrite"]) == 1 and len(calls["audit"]) == 1
    assert evidence["claims"] == GOOD_CLAIMS
    assert evidence["audit"] == {"status": "ok", "model_name": "auditor", "rewritten": False, "unsupported": 0}
    assert evidence["prompt_version"] and "warnings" not in evidence


def test_an_unsupported_claim_earns_one_targeted_rewrite(monkeypatch):
    calls = _scripted(monkeypatch, [INVENTED, CLEAN], [BAD_CLAIMS, GOOD_CLAIMS])
    app, client, job_id = _ready_job()

    generate(app, client, job_id, "resume")

    document = _document(client, job_id)
    assert len(calls["rewrite"]) == 2 and len(calls["audit"]) == 2  # exactly one extra pass, never a loop
    assert any("Globex" in fix for fix in calls["rewrite"][1])
    assert document["content_md"] == CLEAN
    assert document["evidence_map"]["audit"]["rewritten"] is True and "warnings" not in document["evidence_map"]


def test_claims_that_stay_unsupported_are_warnings_and_the_better_draft_is_kept(monkeypatch):
    _scripted(monkeypatch, [INVENTED, INVENTED], [BAD_CLAIMS, BAD_CLAIMS])
    app, client, job_id = _ready_job()

    generate(app, client, job_id, "resume")

    document = _document(client, job_id)
    assert document["content_md"] == INVENTED
    assert document["evidence_map"]["audit"]["rewritten"] is False
    assert document["evidence_map"]["audit"]["unsupported"] == 1
    assert any("Globex" in warning for warning in document["evidence_map"]["warnings"])


def test_a_failing_audit_never_blocks_the_document(monkeypatch):
    _scripted(monkeypatch, [CLEAN], [UserFacingError("The AI service is unavailable")])
    app, client, job_id = _ready_job()

    generate(app, client, job_id, "resume")

    document = _document(client, job_id)
    assert document["content_md"] == CLEAN
    assert document["evidence_map"]["audit"]["status"] == "skipped"
    assert "claims" not in document["evidence_map"]
    assert any("fact check could not run" in warning for warning in document["evidence_map"]["warnings"])


def test_the_audit_can_be_switched_off(monkeypatch):
    calls = _scripted(monkeypatch, [CLEAN], [GOOD_CLAIMS])
    patch_llm_settings(monkeypatch, audit_documents=False)
    app, client, job_id = _ready_job()

    generate(app, client, job_id, "resume")

    assert calls["audit"] == []
    assert "audit" not in _document(client, job_id)["evidence_map"]

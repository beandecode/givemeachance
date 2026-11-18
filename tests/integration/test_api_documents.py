from app import create_app
from tests.support import approved_profile, register, search, top_job


def _client(app, username=None):
    return register(app, username, prefix="docs_api")


def _client_with_evaluated_job(app, username=None):
    client = _client(app, username)
    approved_profile(app, client, candidate_name="Docs User")
    search(app, client)
    return client, top_job(client)


def _generate(app, client, job_id, kind):
    response = client.post(f"/api/v1/jobs/{job_id}/documents", json={"kind": kind})
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["task_id"]
    app.extensions["task_runner"].drain()
    return task_id


def test_generate_view_and_edit_a_resume_keeps_every_version():
    app = create_app()
    client, job_id = _client_with_evaluated_job(app)

    task_id = _generate(app, client, job_id, "resume")
    task = client.get(f"/api/v1/tasks/{task_id}").get_json()["data"]
    assert task["state"] == "succeeded"
    assert task["job_id"] == job_id  # lets the SPA resume progress on the right job after a reload
    assert client.get(f"/api/v1/tasks/{task_id}/result").get_json()["data"]["version"] == 1

    detail = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    generated = detail["documents"]["resume"]
    assert (generated["version"], generated["origin"], generated["version_count"]) == (1, "generated", 1)
    assert detail["decision"]["generate_resume"] is True and detail["decision"]["viewed_match_at"]
    original = client.get(f"/api/v1/documents/resume/{generated['id']}").get_json()["data"]
    assert original["content_md"] and original["kind"] == "resume"

    edited = client.put(f"/api/v1/documents/resume/{generated['id']}", json={"content_md": "# Edited by me"})
    assert edited.status_code == 201
    assert (edited.get_json()["data"]["version"], edited.get_json()["data"]["origin"]) == (2, "edited")

    versions = client.get(f"/api/v1/jobs/{job_id}/documents").get_json()["data"]
    assert [(v["version"], v["origin"]) for v in versions["resume"]] == [(2, "edited"), (1, "generated")]
    assert versions["cover_letter"] == []
    unchanged = client.get(f"/api/v1/documents/resume/{generated['id']}").get_json()["data"]
    assert unchanged["content_md"] == original["content_md"]


def test_documents_of_other_users_are_not_visible():
    app = create_app()
    owner, job_id = _client_with_evaluated_job(app, "docs_owner")
    _generate(app, owner, job_id, "cover_letter")
    document_id = owner.get(f"/api/v1/jobs/{job_id}").get_json()["data"]["documents"]["cover_letter"]["id"]

    stranger = _client(app, "docs_stranger")
    assert stranger.get(f"/api/v1/documents/cover_letter/{document_id}").status_code == 404
    assert stranger.put(f"/api/v1/documents/cover_letter/{document_id}", json={"content_md": "x"}).status_code == 404
    assert stranger.post(f"/api/v1/jobs/{job_id}/documents", json={"kind": "resume"}).status_code == 404
    assert owner.get(f"/api/v1/documents/memo/{document_id}").status_code == 404


def test_application_status_and_note_feed_the_kanban():
    app = create_app()
    client, job_id = _client_with_evaluated_job(app)

    updated = client.patch(f"/api/v1/jobs/{job_id}/application", json={"status": "submitted", "note": "Applied online"})
    assert updated.get_json()["data"]["status"] == "submitted"
    note_only = client.patch(f"/api/v1/jobs/{job_id}/application", json={"note": "Recruiter replied"})
    assert note_only.get_json()["data"] == {**note_only.get_json()["data"], "status": "submitted"}
    assert client.patch(f"/api/v1/jobs/{job_id}/application", json={}).status_code == 400
    assert client.patch(f"/api/v1/jobs/{job_id}/application", json={"status": "ghosted"}).status_code == 400

    cards = {card["job_id"]: card for card in client.get("/api/v1/applications").get_json()["data"]}
    assert cards[job_id]["status"] == "submitted"
    assert cards[job_id]["note"] == "Recruiter replied"


def test_active_task_filter_and_cancel():
    app = create_app()
    client, job_id = _client_with_evaluated_job(app)
    app.extensions["task_runner"] = _NeverRuns()

    task_id = client.post(f"/api/v1/jobs/{job_id}/documents", json={"kind": "resume"}).get_json()["data"]["task_id"]

    active = client.get("/api/v1/tasks?active=true").get_json()["data"]
    assert [task["task_id"] for task in active["items"]] == [task_id]
    assert client.get(f"/api/v1/tasks/{task_id}/result").status_code == 409
    cancelled = client.post(f"/api/v1/tasks/{task_id}/cancel").get_json()["data"]
    assert cancelled["state"] == "cancelled"
    assert client.get("/api/v1/tasks?active=true").get_json()["data"]["total"] == 0


class _NeverRuns:
    """Task runner stand-in that leaves tasks queued."""

    def enqueue(self, task_id, handler):
        pass

    def shutdown(self, wait=True):
        pass

    def drain(self, timeout=None):
        pass


def test_export_pdf_and_docx_downloads():
    app = create_app()
    client, job_id = _client_with_evaluated_job(app)
    _generate(app, client, job_id, "resume")
    document_id = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]["documents"]["resume"]["id"]

    pdf = client.get(f"/api/v1/documents/resume/{document_id}/export?format=pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
    assert 'attachment; filename="' in pdf.headers["Content-Disposition"]
    assert pdf.headers["Content-Disposition"].endswith('-resume-v1.pdf"')

    docx = client.get(f"/api/v1/documents/resume/{document_id}/export?format=docx")
    assert docx.status_code == 200
    assert docx.data.startswith(b"PK")

    assert client.get(f"/api/v1/documents/resume/{document_id}/export?format=odt").status_code == 400
    stranger = _client(app, "export_stranger")
    assert stranger.get(f"/api/v1/documents/resume/{document_id}/export").status_code == 404

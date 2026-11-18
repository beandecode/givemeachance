"""DEMO_LIVE: visitors still read the sample workspace; a guest gets an own, limited, disposable workspace."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
import yaml

from app import create_app
from core.config import load_settings
from core.db import db_conn
from core.demo import GUEST_REFUSED_ENDPOINTS, GUEST_WRITE_ENDPOINTS, START_GUEST_ENDPOINT, assert_demo_safe
from core.guest_service import purge_expired_guests
from core.schemas import Settings
from tests.integration.test_demo_mode import WRITE_METHODS, _demo_settings_file, _seed, _use
from tests.support import finish, generate, top_job

LIMITS = {
    "gemini_daily_limit": 25,
    "adzuna_daily_limit": 3,
    "gemini_global_daily_limit": 100,
    "adzuna_global_daily_limit": 30,
}


def _live_settings_file(directory, **limits):
    """The seeded demo settings (mock providers) with daily limits, as the live demo runs them."""
    raw = yaml.safe_load((directory / "settings.demo.yaml").read_text())
    raw["api_limits"] = {**LIMITS, **limits}
    path = directory / "settings.demo-live.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


@pytest.fixture
def live_app(tmp_path, monkeypatch):
    _seed(tmp_path)
    _use(monkeypatch, _live_settings_file(tmp_path), demo=True)
    monkeypatch.setenv("DEMO_LIVE", "true")
    return create_app()


def _guest(app):
    client = app.test_client()
    response = client.post("/api/v1/demo/guest", json={})
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["user"]["username"].startswith("guest_")
    return client


def test_visitors_keep_the_read_only_sample_workspace(live_app):
    client = live_app.test_client()
    config = client.get("/api/v1/config").get_json()["data"]
    assert (config["demo_mode"], config["demo_live"], config["guest"]) == (True, True, False)
    assert len(client.get("/api/v1/jobs").get_json()["data"]["items"]) == 8
    refused = client.post("/api/v1/searches", json={})
    assert (refused.status_code, refused.get_json()["error_code"]) == (403, 1004)
    assert client.post("/api/v1/session", json={"username": "demo", "password": "whatever123"}).status_code == 403


def test_a_guest_gets_the_sample_profile_and_an_empty_workspace_of_their_own(live_app):
    client = _guest(live_app)
    config = client.get("/api/v1/config").get_json()["data"]
    assert (config["demo_mode"], config["demo_live"], config["guest"]) == (False, True, True)
    profile = client.get("/api/v1/profile").get_json()["data"]["profile"]
    assert profile["review_status"] == "approved"
    assert client.get("/api/v1/jobs").get_json()["data"]["items"] == []
    # Starting again keeps the same workspace; another visitor gets a different one.
    again = client.post("/api/v1/demo/guest", json={}).get_json()["data"]["user"]["id"]
    assert again == client.get("/api/v1/session").get_json()["data"]["user"]["id"]
    assert _guest(live_app).get("/api/v1/session").get_json()["data"]["user"]["id"] != again


def test_a_guest_can_score_a_pasted_job_and_write_documents_but_not_touch_profile_or_accounts(live_app):
    client = _guest(live_app)
    body = {"title": "Backend Engineer", "company": "Acme", "description": "Python, SQL, Flask and AWS. " * 20}
    finish(live_app, client, client.post("/api/v1/jobs/manual", json=body))
    job_id = top_job(client)
    generate(live_app, client, job_id, "resume")
    assert client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]["documents"]["resume"] is not None
    # The sample workspace and other guests do not see it.
    assert len(live_app.test_client().get("/api/v1/jobs").get_json()["data"]["items"]) == 8
    assert _guest(live_app).get(f"/api/v1/jobs/{job_id}").status_code == 404

    for method, path, payload in [
        ("post", "/api/v1/profile/synthesize", {"resume_text": "x"}),
        ("patch", "/api/v1/profile", {}),
        ("post", "/api/v1/account", {"username": "someone", "password": "password123"}),
        ("post", "/api/v1/session", {"username": "demo", "password": "whatever123"}),
    ]:
        response = getattr(client, method)(path, json=payload)
        assert (response.status_code, response.get_json()["error_code"]) == (403, 1004), path

    assert client.delete("/api/v1/session").status_code == 200
    assert client.get("/api/v1/config").get_json()["data"]["guest"] is False


@pytest.mark.parametrize("kind", ["text", "pdf", "docx", "image"])
def test_a_guest_builds_a_profile_from_a_sample_resume_and_answers_its_questions(live_app, kind):
    client = _guest(live_app)
    before = client.get("/api/v1/profile").get_json()["data"]["profile"]["id"]
    _, result = finish(live_app, client, client.post("/api/v1/profile/synthesize", json={"sample": kind}))
    profile = client.get("/api/v1/profile").get_json()["data"]["profile"]
    assert profile["id"] == result["profile_id"] != before and profile["review_status"] == "pending"
    with db_conn(load_settings().app.db_path) as conn:
        stored = conn.execute("SELECT source_bundle_json FROM candidate_profiles WHERE id = ?", (profile["id"],))
        bundle = stored.fetchone()[0]
    assert "Casey Chen" in bundle or "casey-chen" in bundle  # built from the sample, never from the request body

    approved = client.post(f"/api/v1/profile/{profile['id']}/review", json={"review_status": "approved"})
    assert approved.status_code == 200
    answer = {"profile_id": profile["id"], "selected_fields": ["languages"], "answers": {"languages": "French"}}
    finish(live_app, client, client.post("/api/v1/profile/supplement", json=answer))
    assert "French" in client.get("/api/v1/profile").get_json()["data"]["profile"]["master_profile"]["languages"]


def test_sample_resumes_open_in_the_demo_and_are_refused_to_real_accounts(live_app):
    visitor = live_app.test_client()
    for kind, mime in [("pdf", "application/pdf"), ("image", "image/png"), ("text", "text/plain")]:
        response = visitor.get(f"/api/v1/demo/sample-resumes/{kind}")
        assert response.status_code == 200 and response.mimetype == mime and response.data
    assert visitor.get("/api/v1/demo/sample-resumes/other").status_code == 404
    refused = _guest(live_app).post("/api/v1/profile/synthesize", json={"resume_text": "My real résumé"})
    assert (refused.status_code, refused.get_json()["error_code"]) == (403, 1004)
    assert "sample" in refused.get_json()["message"]


def test_every_write_route_is_either_allowed_or_refused_for_guests_on_purpose(live_app):
    endpoints = {rule.endpoint for rule in live_app.url_map.iter_rules() if rule.methods & WRITE_METHODS} - {
        START_GUEST_ENDPOINT
    }
    assert endpoints == GUEST_WRITE_ENDPOINTS | GUEST_REFUSED_ENDPOINTS
    assert not GUEST_WRITE_ENDPOINTS & GUEST_REFUSED_ENDPOINTS

    client = _guest(live_app)
    for rule in live_app.url_map.iter_rules():
        if rule.endpoint not in GUEST_REFUSED_ENDPOINTS:
            continue
        path = re.sub(r"<(?:\w+:)?\w+>", "1", rule.rule)
        for method in rule.methods & WRITE_METHODS:
            response = client.open(path, method=method, json={})
            assert (response.status_code, response.get_json()["error_code"]) == (403, 1004), (method, path)


def test_guest_numbers_are_capped_and_old_guests_are_deleted_with_their_data(live_app, monkeypatch):
    monkeypatch.setenv("DEMO_GUESTS_PER_DAY", "2")
    first = _guest(live_app)
    body = {"title": "Backend Engineer", "company": "Acme", "description": "Python, SQL, Flask and AWS. " * 20}
    finish(live_app, first, first.post("/api/v1/jobs/manual", json=body))
    generate(live_app, first, top_job(first), "resume")
    _guest(live_app)
    full = live_app.test_client().post("/api/v1/demo/guest", json={})
    assert (full.status_code, full.get_json()["error_code"]) == (429, 3005)

    db_path = load_settings().app.db_path
    with db_conn(db_path) as conn:
        assert purge_expired_guests(conn) == 0  # nobody is old enough yet
        assert purge_expired_guests(conn, ttl=timedelta(seconds=-1)) == 2
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username LIKE 'guest_%'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 8  # the sample workspace is intact
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    # A deleted guest falls back to the read-only sample workspace.
    assert first.get("/api/v1/config").get_json()["data"]["guest"] is False
    assert len(first.get("/api/v1/jobs").get_json()["data"]["items"]) == 8


def test_one_address_can_start_only_a_few_guests_a_day(live_app, monkeypatch):
    monkeypatch.setenv("DEMO_GUESTS_PER_CLIENT", "2")
    _guest(live_app)
    _guest(live_app)
    refused = live_app.test_client().post("/api/v1/demo/guest", json={})
    assert (refused.status_code, refused.get_json()["error_code"]) == (429, 3005)
    assert "several times" in refused.get_json()["message"]
    elsewhere = live_app.test_client().post("/api/v1/demo/guest", json={}, environ_base={"REMOTE_ADDR": "203.0.113.9"})
    assert elsewhere.status_code == 201
    with db_conn(load_settings().app.db_path) as conn:  # only a keyed hash of the address is kept
        keys = [row[0] for row in conn.execute("SELECT client_key FROM guest_starts")]
    assert len(keys) == 3 and all(len(key) == 32 and "." not in key for key in keys)


def test_guest_accounts_mean_nothing_outside_the_live_demo(live_app, monkeypatch):
    client = _guest(live_app)
    monkeypatch.setenv("DEMO_LIVE", "false")
    assert client.get("/api/v1/session").get_json()["data"]["user"]["username"] == "demo"
    assert client.post("/api/v1/searches", json={}).status_code == 403
    assert live_app.test_client().post("/api/v1/demo/guest", json={}).status_code == 403


@pytest.mark.parametrize(
    ("limits", "message"),
    [
        ({"gemini_global_daily_limit": 0}, "gemini_global_daily_limit"),
        ({"adzuna_global_daily_limit": 5000}, "adzuna_global_daily_limit"),
        ({"gemini_daily_limit": 200}, "gemini_daily_limit"),
    ],
)
def test_live_demo_refuses_to_start_without_bounded_limits(tmp_path, monkeypatch, limits, message):
    _demo_settings_file(tmp_path)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_LIVE", "true")
    raw = yaml.safe_load(_live_settings_file(tmp_path, **limits).read_text())
    with pytest.raises(RuntimeError, match=message):
        assert_demo_safe(Settings.model_validate(raw))


def test_live_demo_needs_a_real_session_key(tmp_path, monkeypatch):
    _seed(tmp_path)
    _use(monkeypatch, _live_settings_file(tmp_path), demo=True)
    monkeypatch.setenv("DEMO_LIVE", "true")
    monkeypatch.delenv("FLASK_SECRET_KEY")
    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        create_app()

"""DEMO_MODE: a seeded, read-only workspace that never reaches a provider or changes the database."""

from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
from pathlib import Path

import pytest
import yaml

import core.config as config
from app import create_app
from core.demo import assert_demo_safe
from core.schemas import Settings
from tests.conftest import PROJECT_ROOT

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_demo", PROJECT_ROOT / "scripts/seed_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _demo_settings_file(directory: Path) -> Path:
    raw = yaml.safe_load((PROJECT_ROOT / "config/settings.demo.yaml").read_text())
    raw["app"]["db_path"] = str(directory / "demo.db")
    raw["app"]["log_path"] = str(directory / "pipeline.log")
    for key in ("adzuna_file", "jooble_file"):
        raw["mock_data"][key] = str(PROJECT_ROOT / raw["mock_data"][key])
    path = directory / "settings.demo.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


def _seed(directory: Path) -> Path:
    settings_file = _demo_settings_file(directory)
    saved = dict(os.environ)
    try:
        assert _load_seed_module().seed(settings_file) is True
    finally:  # seed() configures the process environment for its own app; undo that
        os.environ.clear()
        os.environ.update(saved)
    return settings_file


def _use(monkeypatch, settings_file: Path, *, demo: bool) -> None:
    monkeypatch.setenv("SETTINGS_FILE", str(settings_file))
    if demo:
        monkeypatch.setenv("DEMO_MODE", "true")
    config.reset_config()


def _row_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tables}


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    settings_file = _seed(tmp_path)
    _use(monkeypatch, settings_file, demo=True)
    app = create_app()
    app.config["TESTING_DB"] = tmp_path / "demo.db"
    return app


def test_demo_visitors_read_the_seeded_workspace_without_signing_in(demo_app):
    client = demo_app.test_client()
    config_data = client.get("/api/v1/config").get_json()["data"]
    assert config_data["demo_mode"] is True
    assert config_data["registration_open"] is False
    assert client.get("/api/v1/session").get_json()["data"]["user"]["username"] == "demo"

    jobs = client.get("/api/v1/jobs").get_json()["data"]["items"]
    assert len(jobs) == 8
    applications = client.get("/api/v1/applications").get_json()["data"]
    assert {item["status"] for item in applications} >= {"interview", "submitted", "offer", "rejected"}
    assert client.get("/api/v1/profile").get_json()["data"]["profile"] is not None
    with_documents = [job for job in jobs if job["application_status"] in {"interview", "offer"}]
    detail = client.get(f"/api/v1/jobs/{with_documents[0]['id']}").get_json()["data"]
    assert detail["documents"]["resume"] is not None and detail["documents"]["cover_letter"] is not None


def test_every_write_is_refused_and_nothing_changes(demo_app):
    db_path = demo_app.config["TESTING_DB"]
    before = _row_counts(db_path)
    client = demo_app.test_client()
    # Read the main pages first so hidden writes on GET would show up in the comparison too.
    for path in ("/api/v1/jobs", "/api/v1/overview", "/api/v1/applications", "/api/v1/tasks", "/api/v1/profile"):
        assert client.get(path).status_code == 200

    checked = 0
    for rule in demo_app.url_map.iter_rules():
        methods = rule.methods & WRITE_METHODS
        if not methods:
            continue
        path = re.sub(r"<int:\w+>", "1", rule.rule)
        path = re.sub(r"<(?:string:)?kind>", "resume", path)
        path = re.sub(r"<(?:\w+:)?\w+>", "1", path)
        for method in methods:
            response = client.open(path, method=method, json={})
            assert response.status_code == 403, (method, path, response.status_code)
            assert response.get_json()["error_code"] == 1004, (method, path)
            checked += 1
    assert checked >= 15  # the sweep must really cover the API
    assert _row_counts(db_path) == before


def test_demo_never_calls_a_provider(demo_app, monkeypatch):
    import adapters.llm.mock_gemini as llm
    from adapters.jobs.mock_adzuna import MockAdzunaAdapter

    def forbidden(*args, **kwargs):
        raise AssertionError("provider called in demo mode")

    for name in ("evaluate", "synthesize_master_profile", "rewrite_resume", "rewrite_cover_letter"):
        monkeypatch.setattr(llm.MockGeminiEvaluator, name, forbidden)
    monkeypatch.setattr(MockAdzunaAdapter, "fetch_jobs", forbidden)
    client = demo_app.test_client()
    for method, path in [
        ("post", "/api/v1/searches"),
        ("post", "/api/v1/evaluations/rerun"),
        ("post", "/api/v1/profile/synthesize"),
        ("post", "/api/v1/jobs/1/documents"),
    ]:
        assert getattr(client, method)(path, json={}).status_code == 403
    for path in ("/api/v1/jobs", "/api/v1/jobs/1", "/api/v1/profile"):
        assert client.get(path).status_code == 200


def test_demo_starts_without_a_secret_key_and_signs_nobody_in(tmp_path, monkeypatch):
    settings_file = _seed(tmp_path)
    _use(monkeypatch, settings_file, demo=True)
    monkeypatch.delenv("FLASK_SECRET_KEY")
    client = create_app().test_client()
    assert client.post("/api/v1/session", json={"username": "demo", "password": "whatever123"}).status_code == 403
    assert client.post("/api/v1/account", json={"username": "someone", "password": "password123"}).status_code == 403


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("llm", "provider", "gemini_api", "llm.provider"),
        ("data_sources", "primary", "adzuna_api", "data_sources.primary"),
        ("api_limits", "gemini_daily_limit", 50, "api_limits.gemini_daily_limit"),
    ],
)
def test_demo_refuses_to_start_with_live_providers_or_quota(tmp_path, monkeypatch, section, key, value, message):
    raw = yaml.safe_load(_demo_settings_file(tmp_path).read_text())
    raw[section][key] = value
    with pytest.raises(RuntimeError, match=message):
        assert_demo_safe(Settings.model_validate(raw))
    path = tmp_path / "unsafe.yaml"
    path.write_text(yaml.safe_dump(raw))
    _use(monkeypatch, path, demo=True)
    with pytest.raises(RuntimeError, match=message):
        create_app()


def test_demo_mode_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    client = create_app().test_client()
    assert client.get("/api/v1/config").get_json()["data"]["demo_mode"] is False
    assert client.get("/api/v1/jobs").status_code == 401


def test_seed_is_deterministic(tmp_path):
    def snapshot(directory: Path):
        directory.mkdir()
        _seed(directory)
        with sqlite3.connect(directory / "demo.db") as conn:
            return {
                "jobs": conn.execute(
                    "SELECT source_job_id, title, company FROM jobs ORDER BY source_job_id"
                ).fetchall(),
                "scores": conn.execute(
                    "SELECT j.source_job_id, e.match_score, e.recommendation_level FROM evaluations e "
                    "JOIN jobs j ON j.id = e.job_id ORDER BY j.source_job_id"
                ).fetchall(),
                "resumes": conn.execute(
                    "SELECT j.source_job_id, r.version, r.content_md FROM generated_resumes r "
                    "JOIN jobs j ON j.id = r.job_id ORDER BY j.source_job_id, r.version"
                ).fetchall(),
                "applications": conn.execute(
                    "SELECT j.source_job_id, a.status, a.status_note FROM applications a "
                    "JOIN jobs j ON j.id = a.job_id ORDER BY j.source_job_id"
                ).fetchall(),
            }

    assert snapshot(tmp_path / "a") == snapshot(tmp_path / "b")

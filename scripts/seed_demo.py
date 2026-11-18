"""Fill the demo database with a deterministic sample workspace (mock providers only).

Usage: python scripts/seed_demo.py [--settings config/settings.demo.yaml] [--force]

Signs up a temporary owner, runs the real product flow against the mock providers (profile, search,
evaluations, documents, application statuses), then renames the owner to the reserved `demo` user that
DEMO_MODE shows to every visitor. Needs no keys and never calls a live provider. Skips when the database
is already seeded unless --force is given.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml
from werkzeug.security import generate_password_hash

OWNER = "demo_seed_owner"
# (job title, application status, status note); other jobs stay unapplied. Documents are generated for these.
APPLICATIONS = [
    ("Backend Python Engineer", "interview", "Phone screen went well; technical round next week."),
    ("Data Engineer", "submitted", "Applied through the company site."),
    ("API Developer (FastAPI)", "ready", "Documents reviewed; send on Monday."),
    ("Senior Platform Engineer", "offer", "Verbal offer received; negotiating."),
    ("Frontend Engineer", "rejected", "Position filled internally."),
]
# A complete profile of a fictional candidate (data/mock/demo_profile.json). Live-demo guests are scored with it by the
# real model, so it carries what a real résumé would: titles, dates, numbers, education and preferences.
PROFILE_FILE = ROOT / "data/mock/demo_profile.json"


def _ok(response, what: str, *, status: int = 200) -> dict:
    payload = response.get_json(silent=True) or {}
    if response.status_code != status:
        raise SystemExit(f"seed failed at {what}: HTTP {response.status_code} {payload}")
    return payload.get("data", payload)


def _task(app, client, response, what: str) -> dict:
    """Wait for the background task a 202 response started and return its result."""
    started = _ok(response, what, status=202)
    app.extensions["task_runner"].drain()
    task = _ok(client.get(f"/api/v1/tasks/{started['task_id']}"), what)
    if task["state"] != "succeeded":
        raise SystemExit(f"seed failed at {what}: task {task['state']}: {task.get('error_message_safe')}")
    return _ok(client.get(f"/api/v1/tasks/{started['task_id']}/result"), what)


def seed(settings_file: Path, force: bool = False) -> bool:
    """Seed the database named by `settings_file`. Returns False when it was already seeded."""
    os.environ.update(
        {
            "SETTINGS_FILE": str(settings_file),
            "FLASK_SECRET_KEY": secrets.token_urlsafe(48),
            "SESSION_COOKIE_SECURE": "false",
            "DEMO_MODE": "false",  # seeding writes; the server is what runs read-only
            "REGISTRATION_MODE": "open",
            "RESUME_FILE": str(ROOT / "config/resume.yaml.example"),
            "SEARCH_PARAMS_FILE": str(ROOT / "config/search_params.yaml"),
            "ADMIN_BOOTSTRAP_USERNAME": "",
            "ADMIN_BOOTSTRAP_PASSWORD": "",
        }
    )
    import core.config as config

    config.load_env_file = lambda: None  # never read config/api-keys.env
    config.reset_config()
    settings = config.load_settings()
    if settings.llm.provider != "mock_gemini":
        raise SystemExit("refusing to seed with a live provider; use mock_gemini")

    db_path = Path(settings.app.db_path)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    if db_path.exists():
        if not force:
            from core.db import db_conn

            with db_conn(str(db_path)) as conn:
                if conn.execute("SELECT 1 FROM users WHERE username = 'demo'").fetchone():
                    return False
        else:
            for suffix in ("", "-wal", "-shm"):
                Path(str(db_path) + suffix).unlink(missing_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    Path(settings.app.log_path).parent.mkdir(parents=True, exist_ok=True)

    from app import create_app
    from core.db import db_conn

    app = create_app()
    client = app.test_client()
    try:
        signup = {"username": OWNER, "password": secrets.token_urlsafe(24)}
        _ok(client.post("/api/v1/account", json=signup), "sign-up", status=201)
        # Saved the way an owner's own edit is saved: a new version that counts as reviewed.
        profile = json.loads(PROFILE_FILE.read_text())
        _ok(client.patch("/api/v1/profile", json={"master_profile": profile}), "profile", status=201)
        search = {"adzuna": {"country": "ca", "keywords": ["backend engineer", "python"], "location": "Ontario"}}
        _ok(client.put("/api/v1/search-preferences", json=search), "search preferences")
        _task(app, client, client.post("/api/v1/searches", json={}), "job search")
        jobs = _ok(client.get("/api/v1/jobs?limit=100"), "job list")["items"]
        by_title = {job["title"]: job["id"] for job in jobs}
        for title, status, note in APPLICATIONS:
            job_id = by_title.get(title)
            if job_id is None:
                raise SystemExit(f"seed failed: job {title!r} not found after search")
            for kind in ("resume", "cover_letter"):
                _task(app, client, client.post(f"/api/v1/jobs/{job_id}/documents", json={"kind": kind}), kind)
            _ok(client.patch(f"/api/v1/jobs/{job_id}/application", json={"status": status, "note": note}), "status")
        # Reads create a few lazily-built tables (quota usage); do it now so the served database never changes.
        for path in ("/api/v1/overview", "/api/v1/tasks"):
            _ok(client.get(path), path)
    finally:
        app.extensions["task_runner"].shutdown()

    # Hand the workspace to the reserved demo user and make sure nobody can ever sign in as it.
    with db_conn(str(db_path)) as conn:
        conn.execute("DELETE FROM users WHERE username = 'demo'")
        conn.execute(
            "UPDATE users SET username = 'demo', password_hash = ? WHERE username = ?",
            (generate_password_hash(secrets.token_urlsafe(32)), OWNER),
        )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--settings", default=str(ROOT / "config/settings.demo.yaml"))
    parser.add_argument("--force", action="store_true", help="delete and rebuild an existing database")
    args = parser.parse_args()
    settings_file = Path(args.settings).resolve()
    yaml.safe_load(settings_file.read_text())  # fail early on a missing/invalid file
    print("Demo workspace seeded." if seed(settings_file, args.force) else "Demo workspace already seeded.")


if __name__ == "__main__":
    main()

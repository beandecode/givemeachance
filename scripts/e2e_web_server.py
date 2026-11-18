"""Throwaway server for the web app's Playwright tests (web/e2e/).

Mock providers, a temporary database, open registration and no personal files or keys, served over HTTP so a
real browser can drive the built app at /app.
Usage: python scripts/e2e_web_server.py [port] [--demo]   (Playwright starts it; see web/playwright.config.ts)
With --demo the database is seeded by scripts/seed_demo.py and served read-only under DEMO_MODE.
"""

from __future__ import annotations

import os
import secrets
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _demo_settings(temp: str) -> Path:
    raw = yaml.safe_load((ROOT / "config/settings.demo.yaml").read_text())
    raw["app"]["db_path"] = str(Path(temp) / "demo.db")
    raw["app"]["log_path"] = str(Path(temp) / "pipeline.log")
    for key in ("adzuna_file", "jooble_file"):
        raw["mock_data"][key] = str(ROOT / raw["mock_data"][key])
    path = Path(temp) / "settings.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


def main() -> None:
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    port = int(args[0]) if args else 5099
    with tempfile.TemporaryDirectory(prefix="gmc-e2e-") as temp:
        if "--demo" in sys.argv:
            sys.path.insert(0, str(ROOT / "scripts"))
            from seed_demo import seed

            settings_file = _demo_settings(temp)
            seed(settings_file)
            os.environ.update({"SETTINGS_FILE": str(settings_file), "DEMO_MODE": "true"})
            from app import create_app

            create_app().run(host="127.0.0.1", port=port, threaded=True)
            return
        raw = yaml.safe_load((ROOT / "config/settings.test.yaml").read_text())
        raw["app"]["db_path"] = str(Path(temp) / "runtime.db")
        raw["app"]["log_path"] = str(Path(temp) / "pipeline.log")
        settings_file = Path(temp) / "settings.yaml"
        settings_file.write_text(yaml.safe_dump(raw))
        os.environ.update(
            {
                "SETTINGS_FILE": str(settings_file),
                "FLASK_SECRET_KEY": secrets.token_urlsafe(48),
                "SESSION_COOKIE_SECURE": "false",
                "REGISTRATION_MODE": "open",
                "RESUME_FILE": str(ROOT / "config/resume.yaml.example"),
                "SEARCH_PARAMS_FILE": str(ROOT / "config/search_params.yaml"),
                "ADMIN_BOOTSTRAP_USERNAME": "",
                "ADMIN_BOOTSTRAP_PASSWORD": "",
                # Slow the mock model down a little so the tests can see (and reload during) running tasks.
                "MOCK_LLM_DELAY_SECONDS": os.environ.get("MOCK_LLM_DELAY_SECONDS", "1.5"),
            }
        )
        import core.config as config

        config.load_env_file = lambda: None  # never read config/api-keys.env
        from app import create_app

        create_app().run(host="127.0.0.1", port=port, threaded=True)


if __name__ == "__main__":
    main()

"""Export the /api/v1 OpenAPI description to docs/openapi.json.

Usage: python scripts/export_openapi.py [--check]
Builds the app with an isolated temporary database and mock settings; no private data is read.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / "docs" / "openapi.json"


def render() -> str:
    import yaml

    with tempfile.TemporaryDirectory() as temp:
        raw = yaml.safe_load((ROOT / "config/settings.test.yaml").read_text())
        raw["app"]["db_path"] = str(Path(temp) / "openapi.db")
        raw["app"]["log_path"] = str(Path(temp) / "openapi.log")
        settings_file = Path(temp) / "settings.yaml"
        settings_file.write_text(yaml.safe_dump(raw))
        os.environ.update(
            SETTINGS_FILE=str(settings_file),
            FLASK_SECRET_KEY="openapi-export-only-0123456789abcdef",  # gitleaks:allow
            ADMIN_BOOTSTRAP_USERNAME="",
            ADMIN_BOOTSTRAP_PASSWORD="",
        )
        import core.config as config

        config.load_env_file = lambda: None  # never read config/api-keys.env
        config.reset_config()
        from app import create_app
        from app.openapi import build_openapi

        app = create_app()
        document = build_openapi(app)
        app.extensions["task_runner"].shutdown(wait=True)
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if docs/openapi.json is out of date")
    args = parser.parse_args()
    rendered = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != rendered:
            print("docs/openapi.json is out of date; run: python scripts/export_openapi.py", file=sys.stderr)
            raise SystemExit(1)
        print("OpenAPI document is current")
    else:
        OUTPUT.write_text(rendered)
        print(f"Exported {len(json.loads(rendered)['paths'])} paths to {OUTPUT.relative_to(ROOT)}")

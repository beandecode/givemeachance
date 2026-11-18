from __future__ import annotations

import os
from pathlib import Path

import yaml

from core.schemas import JobSearchConfig, Settings


def load_env_file() -> None:
    """Load key=value pairs from config/api-keys.env into process environment."""
    env_path = Path(__file__).resolve().parents[1] / "config" / "api-keys.env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _resolve_path(default_relative: str, env_var_name: str) -> Path:
    override = os.getenv(env_var_name)
    if override:
        path = Path(override)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / override
        return path
    return Path(__file__).resolve().parents[1] / default_relative


# Loaded once per process, on first use; tests and scripts call `reset_config()` to reload (or `install_settings`
# to run with a derived copy). The settings themselves are frozen.
_settings: Settings | None = None
_resume: dict | None = None
_search_config: JobSearchConfig | None = None


def reset_config() -> None:
    """Forget everything loaded so the next call reads the files and environment again."""
    global _settings, _resume, _search_config
    _settings = _resume = _search_config = None


def install_settings(settings: Settings) -> None:
    """Use `settings` for the rest of the process (until `reset_config()`)."""
    global _settings
    _settings = settings


def load_settings() -> Settings:
    """Project settings from YAML, loaded once; relative paths are resolved against the project root."""
    global _settings
    if _settings is None:
        _settings = _read_settings()
    return _settings


def _read_settings() -> Settings:
    load_env_file()
    settings_path = _resolve_path("config/settings.yaml", "SETTINGS_FILE")
    settings = Settings.model_validate(yaml.safe_load(settings_path.read_text(encoding="utf-8")))
    root = Path(__file__).resolve().parents[1]

    def absolute(value: str) -> str:
        return value if Path(value).is_absolute() else str(root / value)

    return settings.model_copy(
        update={
            "app": settings.app.model_copy(
                update={"db_path": absolute(settings.app.db_path), "log_path": absolute(settings.app.log_path)}
            ),
            "mock_data": settings.mock_data.model_copy(
                update={
                    "adzuna_file": absolute(settings.mock_data.adzuna_file),
                    "jooble_file": absolute(settings.mock_data.jooble_file),
                }
            ),
        }
    )


def load_resume() -> dict:
    """Structured resume data used for matching and CL generation (loaded once)."""
    global _resume
    if _resume is None:
        load_env_file()
        resume_path = _resolve_path("config/resume.yaml", "RESUME_FILE")
        payload = yaml.safe_load(resume_path.read_text(encoding="utf-8")) if resume_path.exists() else {}
        _resume = payload if isinstance(payload, dict) else {}
    return _resume


def load_job_search_config() -> JobSearchConfig:
    """Default job search parameters used by source adapters (loaded once)."""
    global _search_config
    if _search_config is None:
        load_env_file()
        search_path = _resolve_path("config/search_params.yaml", "SEARCH_PARAMS_FILE")
        _search_config = JobSearchConfig.model_validate(yaml.safe_load(search_path.read_text(encoding="utf-8")))
    return _search_config

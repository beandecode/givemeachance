import sys
from pathlib import Path

# Ensure project root is importable when tests are invoked from any location.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from core.config import load_settings, reset_config


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    """Never load personal credentials/resume or share SQLite/artifacts across tests."""
    import yaml

    import core.config as config
    from core.async_tasks import LocalTaskRunner

    raw = yaml.safe_load((PROJECT_ROOT / "config/settings.test.yaml").read_text())
    raw["app"]["db_path"] = str(tmp_path / "runtime.db")
    raw["app"]["log_path"] = str(tmp_path / "pipeline.log")
    settings_file = tmp_path / "settings.yaml"
    settings_file.write_text(yaml.safe_dump(raw))
    monkeypatch.setenv("SETTINGS_FILE", str(settings_file))
    monkeypatch.setenv("RESUME_FILE", str(PROJECT_ROOT / "config/resume.yaml.example"))
    monkeypatch.setenv("SEARCH_PARAMS_FILE", str(PROJECT_ROOT / "config/search_params.yaml"))
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key-0123456789abcdef0123456789")  # gitleaks:allow
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("REGISTRATION_MODE", "open")
    for key in ("ADMIN_BOOTSTRAP_USERNAME", "ADMIN_BOOTSTRAP_PASSWORD", "ADMIN_BOOTSTRAP_FORCE_RESET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config, "load_env_file", lambda: None)
    runners = []
    original_init = LocalTaskRunner.__init__

    def tracked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        runners.append(self)

    monkeypatch.setattr(LocalTaskRunner, "__init__", tracked_init)
    reset_config()
    yield
    for runner in runners:
        runner.shutdown(wait=True)
    reset_config()


_PROVIDER_ENTRYPOINTS = [
    ("adapters.llm.mock_gemini", "MockGeminiEvaluator", "evaluate"),
    ("adapters.llm.mock_gemini", "MockGeminiEvaluator", "synthesize_master_profile"),
    ("adapters.llm.mock_gemini", "MockGeminiEvaluator", "rewrite_resume"),
    ("adapters.llm.mock_gemini", "MockGeminiEvaluator", "rewrite_cover_letter"),
    ("adapters.jobs.mock_adzuna", "MockAdzunaAdapter", "fetch_jobs"),
    ("adapters.jobs.mock_jooble", "MockJoobleAdapter", "fetch_jobs"),
]


@pytest.fixture(autouse=True)
def provider_calls_hold_no_write_lock(isolated_runtime, monkeypatch):
    """Fail any test in which a provider is called while a database write transaction is open.

    Real provider calls take seconds to minutes; holding SQLite's single writer lock across
    them blocks every other request (roadmap Phase 1b).
    """
    import importlib
    import sqlite3
    import threading

    violations: list[str] = []
    # Probes from concurrent provider calls must not mistake each other's brief lock for a violation.
    probe_lock = threading.Lock()

    def assert_writer_lock_free(label: str) -> None:
        with probe_lock:
            _probe(label)

    def _probe(label: str) -> None:
        db_path = load_settings().app.db_path
        if not Path(db_path).exists():
            return
        probe = sqlite3.connect(db_path, timeout=0, isolation_level=None)
        try:
            probe.execute("BEGIN IMMEDIATE")
            probe.execute("ROLLBACK")
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc):
                raise
            violations.append(label)
        finally:
            probe.close()

    for module_name, class_name, method_name in _PROVIDER_ENTRYPOINTS:
        cls = getattr(importlib.import_module(module_name), class_name)
        original = getattr(cls, method_name)

        def wrapper(self, *args, __original=original, __label=f"{class_name}.{method_name}", **kwargs):
            assert_writer_lock_free(__label)
            return __original(self, *args, **kwargs)

        monkeypatch.setattr(cls, method_name, wrapper)

    yield
    assert not violations, f"provider called while a write transaction was open: {sorted(set(violations))}"


def patch_llm_settings(monkeypatch, **changes):
    """Run with a copy of the loaded settings whose `llm` section has `changes` applied (settings are frozen)."""
    import core.config as config

    current = config.load_settings()
    monkeypatch.setattr(config, "_settings", current.model_copy(update={"llm": current.llm.model_copy(update=changes)}))

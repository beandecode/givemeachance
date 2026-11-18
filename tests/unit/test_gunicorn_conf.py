import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SNIPPET = """
import logging, logging.config, runpy
from gunicorn.glogging import CONFIG_DEFAULTS
conf = runpy.run_path("gunicorn.conf.py")
config = CONFIG_DEFAULTS.copy()
config.update(conf["logconfig_dict"])  # what gunicorn does with it
logging.config.dictConfig(config)
from core.logging_setup import JsonFormatter
handlers = {h.get_name(): h for h in logging.getLogger("gunicorn.error").handlers}
assert isinstance(handlers["error_console"].formatter, JsonFormatter), handlers
assert logging.getLogger().handlers == []
assert not logging.getLogger("gunicorn.error").propagate
print("ok")
"""


def test_the_json_log_config_is_a_valid_gunicorn_logconfig():
    result = subprocess.run(
        [sys.executable, "-c", SNIPPET],
        cwd=ROOT,
        env={"LOG_FORMAT": "json", "PYTHONPATH": str(ROOT), "PATH": ""},
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_without_json_gunicorn_keeps_its_own_logging():
    result = subprocess.run(
        [sys.executable, "-c", "import runpy; print('logconfig_dict' in runpy.run_path('gunicorn.conf.py'))"],
        cwd=ROOT,
        env={"PATH": ""},
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.stdout.strip() == "False", result.stderr

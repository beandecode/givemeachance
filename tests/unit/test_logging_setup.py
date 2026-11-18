import json
import logging
import sys

import pytest

from core.errors import UserFacingError, failure_summary, user_message
from core.logging_setup import JsonFormatter, configure_logging, log_context, log_provider_call, redact


@pytest.mark.parametrize(
    ("raw", "must_not_contain"),
    [
        (
            "GET https://api.adzuna.com/v1/api/jobs/ca/search/1?app_id=abc123&app_key=SECRETKEY99&what=python",
            "SECRETKEY99",
        ),
        ("GET https://api.adzuna.com/x?app_id=abc12345&what=python", "abc12345"),
        ("request failed key=AIzaSyExample-key_123 while calling", "AIzaSyExample"),
        ("headers x-goog-api-key: AIzaSyOther999 sent", "AIzaSyOther999"),
        ("Authorization: Bearer abcdef0123456789token", "abcdef0123456789token"),
        ("owner is casey.chen@example.com today", "casey.chen@example.com"),
        ("call +1-647-555-0137 or (416) 555 0199", "555-0137"),
        ("password=hunter2hunter2", "hunter2"),
    ],
)
def test_redact_masks_secrets_and_personal_details(raw, must_not_contain):
    assert must_not_contain not in redact(raw)


def test_redact_leaves_ordinary_text_alone():
    text = "Evaluated 5 jobs in run manual-search-20261024-223329 at 2026-10-24T22:33:29 (task tsk_af6e4495fb19)"
    assert redact(text) == text


def test_failure_messages_are_redacted_before_they_are_stored_or_shown():
    error = UserFacingError("Adzuna said no: https://api.adzuna.com/search?app_key=TOPSECRET1&what=x")
    assert "TOPSECRET1" not in failure_summary(error)
    assert "TOPSECRET1" not in user_message(error, "req_1")


def test_json_lines_carry_ids_extras_and_masked_text():
    logger = logging.getLogger("test.json")
    record = logger.makeRecord(
        "test.json", logging.INFO, __file__, 1, "sent to %s", ("casey@example.com",), None, extra={"provider": "gemini"}
    )
    with log_context(correlation_id="req_abc", task_id="tsk_1"):
        payload = json.loads(JsonFormatter().format(record))

    assert payload["msg"] == "sent to ***"
    assert (payload["correlation_id"], payload["task_id"], payload["provider"]) == ("req_abc", "tsk_1", "gemini")
    assert payload["level"] == "INFO" and payload["logger"] == "test.json"


def test_tracebacks_are_masked_too():
    try:
        raise RuntimeError("boom app_key=LEAKEDKEY1")
    except RuntimeError:
        record = logging.getLogger("t").makeRecord("t", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())

    assert "LEAKEDKEY1" not in json.loads(JsonFormatter().format(record))["exc"]


def test_provider_calls_log_one_structured_line(caplog):
    import time

    with caplog.at_level(logging.INFO, logger="test.provider"):
        log_provider_call(logging.getLogger("test.provider"), "gemini", "evaluate", 2, time.monotonic(), 429)

    record = caplog.records[0]
    assert (record.provider, record.op, record.attempt, record.status) == ("gemini", "evaluate", 2, "429")
    assert record.latency_ms >= 0


def test_configure_logging_is_idempotent_and_writes_to_the_current_stderr(capsys):
    configure_logging(level="INFO", fmt="json")
    configure_logging(level="INFO", fmt="json")
    marked = [h for h in logging.getLogger().handlers if getattr(h, "_gmc_log_handler", False)]
    assert len(marked) == 1

    logging.getLogger("test.once").warning("hello %s", "world")

    lines = [line for line in capsys.readouterr().err.splitlines() if "hello world" in line]
    assert len(lines) == 1 and json.loads(lines[0])["msg"] == "hello world"

"""Logging for the web process, the task threads and gunicorn.

`configure_logging()` is safe to call more than once. `LOG_FORMAT=json` prints one JSON object per line
(Docker images default to it); anything else prints readable text. Every line carries the request or task
correlation ID, and secrets, e-mail addresses and phone numbers are masked before a line leaves the process.
`redact()` is also what keeps provider details out of stored error messages.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import os
import re
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")
task_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("task_id", default="")

MASK = "***"
_SECRET_PARAM = re.compile(
    r"(?i)\b(app_key|app_id|api[_-]?key|key|token|access_token|secret|password|x-goog-api-key)(\s*[=:]\s*)[^&\s\"',;)]+"
)
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w-])\+?\d{1,3}[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?![\w-])")

# Extra fields a log call may attach (logger.info("...", extra={"provider": "gemini", ...})).
_EXTRA_FIELDS = ("provider", "op", "attempt", "latency_ms", "status")
_HANDLER_MARK = "_gmc_log_handler"


def redact(text: object) -> str:
    """Mask API keys and other secrets in query strings and headers, bearer tokens, e-mail addresses and phones."""
    value = str(text)
    value = _SECRET_PARAM.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", value)
    value = _BEARER.sub(lambda m: f"{m.group(1)}{MASK}", value)
    value = _EMAIL.sub(MASK, value)
    return _PHONE.sub(MASK, value)


@contextlib.contextmanager
def log_context(correlation_id: str | None = None, task_id: str | None = None) -> Iterator[None]:
    """Attach IDs to every log line written inside the block (also in code that has no request)."""
    tokens = []
    if correlation_id is not None:
        tokens.append((correlation_id_var, correlation_id_var.set(correlation_id)))
    if task_id is not None:
        tokens.append((task_id_var, task_id_var.set(task_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def log_provider_call(logger: logging.Logger, provider: str, op: str, attempt: int, started: float, status: object):
    """One line per call to an outside service: who, what, which try, how long, how it ended."""
    latency_ms = round((time.monotonic() - started) * 1000)
    logger.info(
        "%s %s attempt %s -> %s in %s ms",
        provider,
        op,
        attempt,
        status,
        latency_ms,
        extra={"provider": provider, "op": op, "attempt": attempt, "latency_ms": latency_ms, "status": str(status)},
    )


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if correlation_id := correlation_id_var.get():
            payload["correlation_id"] = correlation_id
        if task_id := task_id_var.get():
            payload["task_id"] = task_id
        for field in _EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ids = " ".join(
            f"{name}={value}"
            for name, value in (("correlation_id", correlation_id_var.get()), ("task_id", task_id_var.get()))
            if value
        )
        line = f"{self.formatTime(record, '%Y-%m-%dT%H:%M:%S')} {record.levelname} {record.name}: "
        line += redact(record.getMessage()) + (f" [{ids}]" if ids else "")
        if record.exc_info:
            line += "\n" + redact(self.formatException(record.exc_info))
        return line


class _StderrHandler(logging.StreamHandler):
    """Writes to whatever `sys.stderr` is at the time (tests and servers swap it out)."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


def make_formatter(fmt: str | None = None) -> logging.Formatter:
    chosen: str = fmt if fmt is not None else os.environ.get("LOG_FORMAT", "text")
    return JsonFormatter() if chosen.strip().lower() == "json" else TextFormatter()


def configure_logging(level: str | None = None, fmt: str | None = None) -> None:
    root = logging.getLogger()
    chosen_level: str = level if level is not None else os.environ.get("LOG_LEVEL", "INFO")
    root.setLevel(chosen_level.upper())
    handler = next((h for h in root.handlers if getattr(h, _HANDLER_MARK, False)), None)
    if handler is None:
        handler = _StderrHandler()
        setattr(handler, _HANDLER_MARK, True)
        root.addHandler(handler)
    handler.setFormatter(make_formatter(fmt))

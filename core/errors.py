"""Error messages that may be shown to users.

Raise `UserFacingError` (or a subclass) when the message is written for the person using the
app. Any other exception is an internal failure: log it with its traceback and show only a
generic message with the correlation ID, never `str(exc)` (it may contain SQL, paths or
provider payloads).
"""

from __future__ import annotations

import logging

from core.logging_setup import redact

logger = logging.getLogger(__name__)


class UserFacingError(RuntimeError):
    """An expected failure whose message is safe to display."""


class QuotaExhaustedError(UserFacingError):
    """A daily provider quota is used up; carrying on with the same provider would only fail again."""


def failure_summary(exc: BaseException) -> str:
    """Short, safe description for stored records such as `failed_jobs`."""
    if isinstance(exc, UserFacingError):
        return redact(exc)[:300]
    return f"internal error ({type(exc).__name__}); see server log"


def user_message(exc: BaseException, correlation_id: str) -> str:
    """What to show the user for `exc`."""
    if isinstance(exc, UserFacingError):
        return redact(exc)[:300]
    return f"Something went wrong (ref {correlation_id})"


class ApiError(UserFacingError):
    """An error response from the JSON API: HTTP status, catalog code (docs/error-codes.md) and safe message."""

    def __init__(self, status: int, code: int, message: str, details: list[dict] | None = None):
        super().__init__(message)
        self.status = int(status)
        self.code = int(code)
        self.message = str(message)
        self.details = details


# Catalog code for generic HTTP errors raised by Flask/Werkzeug (unknown route, wrong method, ...).
HTTP_STATUS_CODES = {
    400: 2001,
    401: 1001,
    403: 1003,
    404: 3003,
    405: 2005,
    409: 3004,
    413: 2006,
    415: 2004,
    429: 3005,
}


def code_for_http_status(status: int) -> int:
    if status in HTTP_STATUS_CODES:
        return HTTP_STATUS_CODES[status]
    return 5001 if status >= 500 else 2001

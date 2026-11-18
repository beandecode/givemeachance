"""Request correlation IDs."""

from __future__ import annotations

import re
import uuid

from flask import request

_correlation_id_pattern = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def _resolve_correlation_id(default: str | None = None) -> str:
    candidate = str(request.headers.get("X-Correlation-ID", "")).strip()
    if candidate and _correlation_id_pattern.fullmatch(candidate):
        return candidate
    if default:
        normalized = str(default).strip()
        if normalized and _correlation_id_pattern.fullmatch(normalized):
            return normalized
    return f"req_{uuid.uuid4().hex[:24]}"

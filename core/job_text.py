"""Job posting text helpers."""

from __future__ import annotations

import hashlib

# Adzuna's search API returns only the first 500 characters of a posting and marks the cut with an ellipsis.
_SNIPPET_MAX_LENGTH = 520
MIN_FULL_DESCRIPTION_LENGTH = 200


def is_description_snippet(source: str, description: str) -> bool:
    """True when `description` is only the short preview a job board search returns, not the whole posting."""
    text = str(description or "").rstrip()
    return str(source) == "adzuna" and len(text) <= _SNIPPET_MAX_LENGTH and text.endswith(("…", "..."))


def description_hash(title: str, company: str, description: str) -> str:
    """Same recipe as `core.ingest._description_hash`, for a job that is already stored."""
    return hashlib.sha256(f"{title}|{company}|{description}".encode()).hexdigest()

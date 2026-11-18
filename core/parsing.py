"""Small parsers shared by services: JSON-or-text columns and profile field names."""

from __future__ import annotations

import json
from typing import Any


def parse_list_field(raw: Any) -> list[str]:
    """A list stored as a JSON array, a Python list, or newline-separated text."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_dict_field(raw: Any) -> dict:
    """A dict stored as a JSON object or a Python dict; anything else is empty."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {}


def is_core_high_field(field: Any) -> bool:
    """Fields whose absence blocks search: the name, the core skills and the experience list itself.

    Questions about parts of an entry (`experiences.0.achievements`, a project metric, ...) never block.
    """
    return str(field or "").strip().lower() in {"identity.name", "core_skills", "experiences"}

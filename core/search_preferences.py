from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.config import load_job_search_config
from core.schemas import JobSearchConfig
from core.seniority import default_levels
from core.time_utils import utc_now_iso

SEARCH_PROVIDER_ADZUNA = "adzuna"


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _json_loads_dict(raw: str | None) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def validate_search_preferences(payload: dict[str, Any]) -> JobSearchConfig:
    return JobSearchConfig.model_validate(payload)


def get_user_search_preferences(
    conn: sqlite3.Connection,
    user_id: int,
    provider: str = SEARCH_PROVIDER_ADZUNA,
) -> JobSearchConfig | None:
    row = conn.execute(
        """
        SELECT params_json
        FROM user_search_preferences
        WHERE user_id = ? AND provider = ?
        """,
        (int(user_id), str(provider)),
    ).fetchone()
    if row is None:
        return None
    return validate_search_preferences(_json_loads_dict(row["params_json"]))


def get_effective_search_config(
    conn: sqlite3.Connection | None = None,
    user_id: int | None = None,
) -> tuple[JobSearchConfig, str]:
    if conn is not None and user_id is not None:
        user_config = get_user_search_preferences(conn, int(user_id))
        if user_config is not None:
            return user_config, "user"
    return load_job_search_config(), "default"


def upsert_user_search_preferences(
    conn: sqlite3.Connection,
    user_id: int,
    config: JobSearchConfig,
    provider: str = SEARCH_PROVIDER_ADZUNA,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO user_search_preferences (
            user_id, provider, params_json, created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, provider) DO UPDATE SET
            params_json = excluded.params_json,
            updated_at_utc = excluded.updated_at_utc
        """,
        (
            int(user_id),
            str(provider),
            _json_dumps(config.model_dump(exclude_none=True)),
            now,
            now,
        ),
    )


def suggest_search_config(conn: sqlite3.Connection, user_id: int) -> JobSearchConfig:
    """Effective settings with keywords and location prefilled from the latest Master Profile.

    Used to pre-fill the search form during onboarding; nothing is saved.
    """
    config, _ = get_effective_search_config(conn, user_id)
    row = conn.execute(
        "SELECT master_profile_json FROM candidate_profiles WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    if row is None:
        return config
    try:
        profile = json.loads(str(row["master_profile_json"] or "{}"))
    except json.JSONDecodeError:
        return config
    if not isinstance(profile, dict):
        return config

    def known(value: object) -> str:
        text = str(value or "").strip()
        return "" if text.lower() in {"", "unknown", "n/a", "none"} else text

    raw_preferences, raw_identity = profile.get("preferences"), profile.get("identity")
    preferences: dict = raw_preferences if isinstance(raw_preferences, dict) else {}
    identity: dict = raw_identity if isinstance(raw_identity, dict) else {}
    roles = [known(role) for role in preferences.get("target_roles") or [] if known(role)]
    keywords = roles[:5] or ([known(identity.get("current_title"))] if known(identity.get("current_title")) else [])
    locations = [known(place) for place in preferences.get("preferred_locations") or [] if known(place)]
    location = locations[0] if locations else known(identity.get("location"))

    params = config.adzuna.model_copy()
    if keywords:
        params.keywords = keywords
    if location:
        params.location = location
    # Newest-first returns whatever was posted last at any level; relevance puts the best title matches first.
    params.sort_by = "relevance"
    return JobSearchConfig(adzuna=params, target_levels=default_levels(profile))

"""A cheap relevance score (0 to 100) from the profile and the posting's title and preview, with no AI call.

It decides which jobs to score first when a search is limited (`score_limit`) and how the "Not scored" list is
ordered. It is a ranking aid, not a verdict: the AI score still decides what is a good match.
"""

from __future__ import annotations

import json
import re
import sqlite3

_STOP = {"and", "the", "for", "with", "of", "to", "in", "at", "a", "an", "sr", "jr", "ii", "iii"}
_UNKNOWN = {"", "unknown", "n/a", "none"}


def _tokens(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9+#.]+", text.casefold()) if len(word) >= 2 and word not in _STOP}


def _known(values: object) -> list[str]:
    items = values if isinstance(values, list) else []
    return [str(item).strip() for item in items if str(item).strip().casefold() not in _UNKNOWN]


def profile_terms(master_profile: dict | None) -> tuple[list[str], list[str]]:
    """(target role titles, skills) from a Master Profile; the current title counts as a role."""
    profile = master_profile or {}
    raw_preferences, raw_identity = profile.get("preferences"), profile.get("identity")
    preferences: dict = raw_preferences if isinstance(raw_preferences, dict) else {}
    identity: dict = raw_identity if isinstance(raw_identity, dict) else {}
    roles = _known(preferences.get("target_roles"))
    roles += _known([identity.get("current_title")])
    return roles, _known(profile.get("core_skills"))


def relevance(title: str, description: str, roles: list[str], skills: list[str]) -> int:
    """Role words in the title (50), skills in the text (40), a skill in the title (10)."""
    title_words = _tokens(title)
    role_part = 0.0
    for role in roles:
        words = _tokens(role)
        if words:
            role_part = max(role_part, len(words & title_words) / len(words))

    haystack = f"{title} {description}".casefold()
    in_text = [s for s in skills if re.search(rf"(?<![a-z0-9]){re.escape(s.casefold())}(?![a-z0-9])", haystack)]
    in_title = any(re.search(rf"(?<![a-z0-9]){re.escape(s.casefold())}(?![a-z0-9])", title.casefold()) for s in skills)
    skill_part = min(1.0, len(in_text) / 3)
    return round(50 * role_part + 40 * skill_part + (10 if in_title else 0))


def rank_by_relevance(conn: sqlite3.Connection, job_ids: list[int], profile_row: sqlite3.Row | None) -> list[int]:
    """Store each job's relevance and return the ids best first (ties keep their order), so a limit takes the best."""
    if not job_ids:
        return []
    try:
        profile = json.loads(str(profile_row["master_profile_json"] or "{}")) if profile_row is not None else {}
    except json.JSONDecodeError:
        profile = {}
    roles, skills = profile_terms(profile if isinstance(profile, dict) else {})
    placeholders = ",".join("?" * len(job_ids))
    rows = conn.execute(f"SELECT id, title, description FROM jobs WHERE id IN ({placeholders})", job_ids).fetchall()
    scores = {int(row["id"]): relevance(row["title"], row["description"] or "", roles, skills) for row in rows}
    for job_id, score in scores.items():
        conn.execute("UPDATE jobs SET relevance = ? WHERE id = ?", (score, job_id))
    return sorted(job_ids, key=lambda job_id: -scores.get(job_id, 0))

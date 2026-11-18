"""Search settings suggested by the reasons behind a user's skips (ADR-017). Suggestions are never applied silently."""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from core.prefilter import profile_terms
from core.search_preferences import get_effective_search_config

MIN_SKIPS = 3  # the same reason this many times before anything is suggested
MAX_WORD_SUGGESTIONS = 3
_STOP = {"and", "the", "for", "with", "of", "to", "in", "at", "a", "an", "sr", "jr", "ii", "iii", "i", "&", "-", "/"}
_UP_LEVELS = ("management", "staff_plus", "senior")  # highest first


def _reasons(conn: sqlite3.Connection, user_id: int) -> dict[str, list[str]]:
    """Reason -> titles of the jobs the user skipped for it."""
    rows = conn.execute(
        """SELECT t.reason, j.title FROM job_triage t JOIN jobs j ON j.id = t.job_id
           WHERE t.user_id = ? AND t.action = 'skipped' AND t.reason IS NOT NULL""",
        (user_id,),
    ).fetchall()
    found: dict[str, list[str]] = {}
    for row in rows:
        found.setdefault(str(row["reason"]), []).append(str(row["title"]))
    return found


def _profile_words(conn: sqlite3.Connection, user_id: int) -> set[str]:
    row = conn.execute(
        "SELECT master_profile_json FROM candidate_profiles WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
    ).fetchone()
    try:
        profile = json.loads(str(row["master_profile_json"] or "{}")) if row is not None else {}
    except json.JSONDecodeError:
        profile = {}
    roles, skills = profile_terms(profile if isinstance(profile, dict) else {})
    return {word for text in [*roles, *skills] for word in re.findall(r"[a-z0-9+#.]+", text.casefold())}


def search_suggestions(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    reasons = _reasons(conn, user_id)
    config, _ = get_effective_search_config(conn, user_id)
    suggestions: list[dict[str, Any]] = []

    senior = len(reasons.get("too_senior", []))
    if senior >= MIN_SKIPS:
        highest = next((level for level in _UP_LEVELS if level in config.target_levels), None)
        if highest is not None:
            suggestions.append({"kind": "remove_level", "value": highest, "count": senior})
    if len(reasons.get("too_junior", [])) >= MIN_SKIPS and "junior" in config.target_levels:
        suggestions.append({"kind": "remove_level", "value": "junior", "count": len(reasons["too_junior"])})

    titles = reasons.get("wrong_field", [])
    if len(titles) >= MIN_SKIPS:
        known = _profile_words(conn, user_id) | {word.casefold() for word in config.exclude_title_words} | _STOP
        counts: dict[str, int] = {}
        for title in titles:
            for word in {w for w in re.findall(r"[a-z][a-z0-9+#.]+", title.casefold()) if len(w) >= 3}:
                if word not in known:
                    counts[word] = counts.get(word, 0) + 1
        common = sorted(((n, w) for w, n in counts.items() if n >= 2), key=lambda item: (-item[0], item[1]))
        suggestions += [{"kind": "exclude_word", "value": w, "count": n} for n, w in common[:MAX_WORD_SUGGESTIONS]]
    return suggestions

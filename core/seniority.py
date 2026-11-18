"""Job levels: read the level a job title asks for and suggest which levels suit a candidate.

The user decides which levels to score (`JobSearchConfig.target_levels`; empty means all). Titles that name a
level the user did not pick are dropped before anything is stored or scored. A title without any level word
counts as `mid`.
"""

from __future__ import annotations

import re
from datetime import date

from core.schemas import JobLevel

LEVELS: tuple[JobLevel, ...] = ("junior", "mid", "senior", "staff_plus", "management")

# Highest first: "Senior Engineering Manager" is a management role, "Senior Staff Engineer" a staff one.
_TITLE_PATTERNS: tuple[tuple[JobLevel, re.Pattern[str]], ...] = (
    (
        "management",
        re.compile(
            # "Account Manager" or "Case Manager" is an individual role; see _INDIVIDUAL_MANAGER.
            r"\b(?:manager|director|head of|head|vp|vice president|chief|cto)\b",
            re.IGNORECASE,
        ),
    ),
    ("staff_plus", re.compile(r"\b(?:staff|principal|distinguished|fellow)\b", re.IGNORECASE)),
    ("senior", re.compile(r"\b(?:senior|sr|lead)\b", re.IGNORECASE)),
    (
        "junior",
        re.compile(r"\b(?:junior|jr|intern|internship|entry[- ]level|graduate|trainee|apprentice)\b", re.IGNORECASE),
    ),
)

_UNKNOWN = {"", "unknown", "n/a", "none"}
# Internships, co-ops, volunteering and student roles do not count towards years of professional experience.
_NOT_WORK_YEARS = re.compile(
    r"\b(?:intern|internship|co-?op|volunteer|student|teaching assistant|research assistant)\b", re.I
)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_RANGE = re.compile(r"\d\s*(?:-|–|to)\s*\d")


# Titles named "... Manager" that usually manage accounts, cases, projects or products, not people.
_INDIVIDUAL_MANAGER = re.compile(
    r"\b(?:account|accounts|client|customer success|relationship|case|care|project|program|programme|product|"
    r"property|office|community|social media|content|category|territory|portfolio|sales|marketing|event|events|"
    r"payroll|claims|facilities|logistics|inventory|quality|risk|compliance|campaign|brand)\s+manager\b",
    re.IGNORECASE,
)
_PEOPLE_MANAGER = re.compile(r"\b(?:director|head|vp|vice president|chief|cto|general manager|managing)\b", re.I)


def title_level(title: str) -> JobLevel:
    text = title or ""
    if _INDIVIDUAL_MANAGER.search(text) and not _PEOPLE_MANAGER.search(text):
        text = _INDIVIDUAL_MANAGER.sub(" ", text)  # the remaining words (for example "Senior") decide the level
    for level, pattern in _TITLE_PATTERNS:
        if pattern.search(text):
            return level
    return "mid"


def title_allowed(title: str, levels: list[JobLevel] | None) -> bool:
    """True when `levels` is empty (all levels) or contains the level the title asks for."""
    return not levels or title_level(title) in levels


def parse_years(text: object) -> float | None:
    """ "5", "5+ years", "3-5 years" -> a number of years; None when there is nothing to read."""
    raw = str(text or "").strip()
    if raw.casefold() in _UNKNOWN:
        return None
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", raw)]
    if not numbers:
        return None
    if len(numbers) >= 2 and _RANGE.search(raw):
        return (numbers[0] + numbers[1]) / 2
    return numbers[0]


def years_from_experiences(experiences: object, today: date | None = None) -> float | None:
    """Years between the earliest start year in the profile's experiences and today."""
    if not isinstance(experiences, list):
        return None
    current_year = (today or date.today()).year
    starts = []
    for item in experiences:
        if not isinstance(item, dict) or _NOT_WORK_YEARS.search(
            f"{item.get('employment_type', '')} {item.get('title', '')}"
        ):
            continue
        for key in ("start_date", "duration"):
            match = _YEAR.search(str(item.get(key, "")))
            if match:
                starts.append(int(match.group()))
                break
    if not starts:
        return None
    return float(min(50, max(0, current_year - min(starts))))


def default_levels(master_profile: dict, today: date | None = None) -> list[JobLevel]:
    """Levels that usually suit the candidate; empty (all levels) when the profile gives no hint."""
    identity = master_profile.get("identity")
    years = parse_years(identity.get("years_experience") if isinstance(identity, dict) else None)
    if years is None:
        years = years_from_experiences(master_profile.get("experiences"), today)
    if years is None:
        return []
    # Wide on purpose: a job that is never scored is never seen, and candidates are often hired a level above or
    # below their years. Titles without a level word ("mid") are always kept; the scorer judges the real level.
    if years < 2:
        return ["junior", "mid"]
    if years < 5:
        return ["junior", "mid", "senior"]
    if years < 10:
        return ["mid", "senior", "staff_plus"]
    return ["mid", "senior", "staff_plus", "management"]

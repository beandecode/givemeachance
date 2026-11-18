"""How an evaluation's numbers fit together.

The model only judges each dimension (0-100) against a written rubric. The total, the cap for missing
must-haves and the recommendation are computed here, so they cannot contradict the dimensions and mean the
same thing from one run to the next.
"""

from __future__ import annotations

DIMENSION_WEIGHTS: dict[str, float] = {
    "skills_match": 0.35,
    "experience_match": 0.25,
    "seniority_match": 0.20,
    "domain_match": 0.10,
    "location_salary_match": 0.10,
}
DIMENSIONS = tuple(DIMENSION_WEIGHTS)

# A posting with a mandatory requirement the candidate lacks can still be "maybe", never a good match.
MISSING_MUST_HAVE_CAP = 59

SENIORITY_GAP_FLAGS = {
    "role_is_more_senior": "The role looks more senior than your experience",
    "role_is_less_senior": "The role looks less senior than your experience",
}


def total_score(dimension_scores: dict[str, int], missing_must_haves: list[str]) -> int:
    total = round(sum(dimension_scores[name] * weight for name, weight in DIMENSION_WEIGHTS.items()))
    total = max(0, min(100, total))
    return min(total, MISSING_MUST_HAVE_CAP) if missing_must_haves else total


def recommendation_for(score: int) -> str:
    if score >= 85:
        return "strong_yes"
    if score >= 70:
        return "yes"
    if score >= 55:
        return "maybe"
    return "no"

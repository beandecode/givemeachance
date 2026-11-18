"""Deterministic field coverage; this score does not certify factual accuracy.

Keep the existing weights so this change removes model authority without silently
introducing a new product rubric. Truthfulness and evidence quality need separate
checks; a structurally populated field can still contain incorrect information.
"""


def compute_profile_completeness(profile: dict) -> int:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    contact = identity.get("contact") if isinstance(identity.get("contact"), dict) else {}
    preferences = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
    name = str(identity.get("name") or "").strip().lower()
    score = 15 if name not in {"", "unknown", "n/a", "none", "null", "not provided"} else 0
    for field, weight in (
        ("core_skills", 20),
        ("experiences", 25),
        ("education", 10),
        ("certifications", 10),
        ("projects", 5),
        ("evidence_notes", 5),
    ):
        if isinstance(profile.get(field), list) and profile[field]:
            score += weight
    if isinstance(contact.get("links"), list) and contact["links"]:
        score += 5
    if isinstance(preferences.get("target_roles"), list) and preferences["target_roles"]:
        score += 5
    return score


def with_computed_completeness(profile: dict) -> dict:
    return {
        **profile,
        "completeness_score": compute_profile_completeness(profile),
        "completeness_score_source": "application_field_coverage_v1",
    }

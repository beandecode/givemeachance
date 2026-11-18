import json

from core.generate_resume import parse_master_profile_row
from core.profile_quality import compute_profile_completeness
from core.profile_readiness import assess_profile_readiness
from core.profile_synthesis import _normalize_master_profile


def test_model_cannot_award_itself_complete_profile():
    profile = _normalize_master_profile({"completeness_score": 100}, {}, [], "mock")
    assert profile["completeness_score"] == 0
    assert profile["completeness_score_source"] == "application_field_coverage_v1"


def test_stored_model_score_is_recomputed_without_rewriting_history():
    raw = {"identity": {"name": "Candidate"}, "completeness_score": 100}
    row = {"master_profile_json": json.dumps(raw)}
    assert parse_master_profile_row(row)["completeness_score"] == 15
    assert assess_profile_readiness(raw, {"review_status": "approved"})["completeness_score"] == 15
    assert json.loads(row["master_profile_json"])["completeness_score"] == 100


def test_placeholder_and_wrong_type_values_do_not_count_as_populated_sections():
    assert compute_profile_completeness({"identity": {"name": "Unknown"}, "core_skills": "unknown"}) == 0


def test_placeholders_are_removed_before_generation():
    from core.profile_synthesis import without_placeholders

    profile = {
        "identity": {"name": "Casey", "location": "unknown", "contact": {"email": "N/A", "phone": ""}},
        "experiences": [{"company": "unknown", "title": "Engineer", "highlights": ["Built APIs", "none"]}],
        "core_skills": ["Python", "unknown"],
        "completeness_score": 0,
    }

    assert without_placeholders(profile) == {
        "identity": {"name": "Casey"},
        "experiences": [{"title": "Engineer", "highlights": ["Built APIs"]}],
        "core_skills": ["Python"],
        "completeness_score": 0,
    }


def test_skills_from_text_do_not_duplicate_model_skills_with_different_case():
    profile = _normalize_master_profile(
        {"core_skills": ["python", "Sql", "Aws"]},
        {"resume_text": "Python SQL AWS Docker", "user_details": {"key_skills": "Python, SQL, AWS, Docker"}},
        [],
        "mock",
    )

    skills = [skill.casefold() for skill in profile["core_skills"]]
    assert len(skills) == len(set(skills))
    assert {"python", "sql", "aws", "docker"} <= set(skills)

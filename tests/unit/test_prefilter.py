from core.prefilter import profile_terms, relevance

ROLES = ["Backend Engineer"]
SKILLS = ["Python", "SQL", "Flask"]


def test_a_matching_title_and_skills_score_high_and_an_unrelated_job_low():
    strong = relevance("Backend Python Engineer", "Flask and SQL services", ROLES, SKILLS)
    weak = relevance("Pastry Chef", "Bake bread daily", ROLES, SKILLS)
    assert strong >= 90 and weak == 0


def test_skills_match_whole_words_only():
    assert relevance("Engineer", "We use PythonScript and SQLite", [], SKILLS) == 0


def test_more_matching_skills_rank_higher_and_the_score_stays_in_range():
    one = relevance("Developer", "Python only", [], SKILLS)
    three = relevance("Developer", "Python, SQL and Flask", [], SKILLS)
    assert 0 <= one < three <= 100


def test_profile_terms_ignore_unknown_values():
    profile = {
        "preferences": {"target_roles": ["Backend Engineer", "unknown"]},
        "identity": {"current_title": "N/A"},
        "core_skills": ["Python", "", "none"],
    }
    assert profile_terms(profile) == (["Backend Engineer"], ["Python"])

"""Skills the code adds to a profile from raw text must be whole words (no "aws" in "laws")."""

from core.profile_synthesis import _extract_skills_from_text


def test_hints_match_whole_words_only():
    assert _extract_skills_from_text("Studied laws and clusters of nodes; reactive systems; sparked interest") == []


def test_real_mentions_are_found_including_punctuation():
    found = _extract_skills_from_text("Built APIs in Python/Flask on AWS, with Node.js and machine learning.")
    assert {"Python", "Flask", "AWS", "Node.js", "Machine Learning"} <= set(found)


def test_ordinary_words_in_other_fields_add_no_skill():
    text = "Assessed lymph node swelling; taught students to react calmly; azure blue signage; a spark of curiosity"
    assert _extract_skills_from_text(text) == []


def test_profile_bullets_and_credentials_are_never_cut_at_commas():
    from core.profile_synthesis import _normalize_string_list

    bullets = [
        "Rebuilt ETL jobs with retries, idempotent loads and alerting; on-time delivery rose to 99.6%",
        "Registered Nurse (College of Nurses of Ontario, 2021)",
    ]
    assert _normalize_string_list(bullets) == bullets
    assert _normalize_string_list(["Python, SQL, AWS"]) == ["Python", "SQL", "AWS"]
    assert _normalize_string_list("Python, SQL\nLed the move, cutting latency by 76%") == [
        "Python",
        "SQL",
        "Led the move, cutting latency by 76%",
    ]

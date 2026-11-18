from core.profile_readiness import assess_profile_readiness

APPROVED = {"id": 1, "profile_version": 1, "review_status": "approved"}


def _profile(**overrides):
    base = {
        "identity": {"name": "Casey Chen"},
        "core_skills": ["Python", "SQL", "Flask"],
        "experiences": [{"company": "Acme", "title": "Engineer"}],
        "missing_information": [],
    }
    return {**base, **overrides}


def test_only_the_three_essentials_count_as_high_priority_questions():
    questions = [
        {"field": "experiences.0.achievements", "priority": "high", "question": "Any metrics?"},
        {"field": "projects.1.impact", "priority": "high", "question": "Impact?"},
    ]
    result = assess_profile_readiness(_profile(missing_information=questions), APPROVED)
    assert result["high_priority_missing_count"] == 0


def test_an_empty_experience_list_is_still_a_high_priority_question():
    questions = [{"field": "experiences", "priority": "high", "question": "Describe a job"}]
    result = assess_profile_readiness(_profile(experiences=[], missing_information=questions), APPROVED)
    assert result["high_priority_missing_count"] == 1
    assert result["minimum_ready"] is False
    assert "experiences is empty" in result["minimum_blocking_reasons"]


def test_low_completeness_blocks_search_but_not_the_minimum():
    result = assess_profile_readiness(_profile(), APPROVED)  # no education/projects, so completeness stays low
    assert result["allowed"] is False
    assert result["minimum_ready"] is True
    assert result["minimum_blocking_reasons"] == []


def test_an_unapproved_profile_fails_the_minimum_too():
    result = assess_profile_readiness(_profile(), {**APPROVED, "review_status": "pending"})
    assert result["minimum_ready"] is False
    assert result["minimum_blocking_reasons"] == ["latest master profile has not been approved"]


def test_a_missing_profile_fails_the_minimum():
    result = assess_profile_readiness(None)
    assert result["minimum_ready"] is False
    assert result["minimum_blocking_reasons"] == ["master profile not found"]

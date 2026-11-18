import pytest

from core.document_checks import check_generated_document

PROFILE = {
    "identity": {"name": "Casey Chen"},
    "core_skills": ["Python"],
    "experiences": [{"company": "Acme", "highlights": ["Cut latency by 40%", "Served 2,000 requests per second"]}],
}
JOB = {"title": "Backend Engineer", "company": "Affirm, Inc.", "description": "Build APIs for 5 teams."}
LETTER = (
    "Dear Hiring Manager, I want to join Affirm as a Backend Engineer. "
    + "I build reliable APIs. " * 60
    + "Sincerely, Casey Chen"
)


def _check(kind, text, **kwargs):
    return check_generated_document(kind, text, kwargs.get("profile", PROFILE), JOB, kwargs.get("report"))


@pytest.mark.parametrize(
    "text",
    [
        "Worked at [Company] for years",
        "Salary: N/A",
        "Location: unknown",
        "Start date TBD",
        "Hello {{name}}",
        "Lorem ipsum dolor",
    ],
)
def test_leftover_placeholders_are_violations(text):
    assert _check("resume", f"# Casey Chen\n\n{text}").violations


def test_markdown_links_and_normal_prose_are_not_placeholders():
    text = "# Casey Chen\n\nSee [my portfolio](https://example.com). Built unknown-proof APIs? no: built stable APIs."
    assert not [v for v in _check("resume", text).violations if "placeholder" in v]
    assert _check("resume", "# Casey Chen\n\nBuilt stable APIs in Python.").violations == []


def test_a_cover_letter_must_name_the_company_even_without_its_legal_suffix():
    assert _check("cover_letter", LETTER).violations == []
    without = LETTER.replace("Affirm", "your company")
    assert any("company" in v for v in _check("cover_letter", without).violations)
    assert _check("resume", "# Casey Chen\n\nPython.").violations == []  # résumés need not name it


def test_an_unknown_company_is_not_demanded():
    job = {**JOB, "company": "Unknown"}
    assert check_generated_document("cover_letter", LETTER.replace("Affirm", "them"), PROFILE, job).violations == []


def test_a_letter_far_outside_the_asked_length_is_a_violation():
    assert any("words" in v for v in _check("cover_letter", LETTER + "More words here. " * 200).violations)
    short = _check("cover_letter", "Dear team at Affirm, I would love to talk. Casey Chen").violations
    assert len(short) == 1 and "only 11 words" in short[0]


def test_a_letter_must_be_signed_with_the_profile_name():
    unsigned = _check("cover_letter", LETTER.replace("Casey Chen", "Casy Chen")).violations
    assert len(unsigned) == 1 and "Casey Chen" in unsigned[0]
    assert _check("cover_letter", LETTER, profile={**PROFILE, "identity": {}}).violations == []


def test_stock_phrases_are_a_violation():
    text = LETTER.replace("I want to join", "I am writing to express my enthusiastic interest in joining")
    stock = _check("cover_letter", text).violations
    assert len(stock) == 1 and "i am writing to" in stock[0] and "express my enthusiastic interest" in stock[0]


def test_numbers_from_the_profile_are_fine_in_a_resume():
    check = _check("resume", "# Casey Chen\n\nCut latency by 40% and served 2000 requests per second.")
    assert check.warnings == []


def test_numbers_from_the_posting_or_the_report_are_fine_in_a_cover_letter_but_not_a_resume():
    text = LETTER + " I built APIs for 5 teams and scored 71/100 on fit."
    assert _check("cover_letter", text, report={"match_score": 71}).warnings == []

    resume = _check("resume", "# Casey Chen\n\nBuilt APIs for 5 teams. Score 71/100.", report={"match_score": 71})
    assert len(resume.warnings) == 1 and "5" in resume.warnings[0] and "71" in resume.warnings[0]


def test_an_invented_number_is_only_a_warning():
    check = _check("resume", "# Casey Chen\n\nGrew revenue by 300% and led 12 engineers.")

    assert check.violations == []
    assert len(check.warnings) == 1
    assert "300" in check.warnings[0] and "12" in check.warnings[0]


def _with_experience(**profile):
    return {
        "experiences": [{"company": "Acme Corp", "title": "Backend Engineer"}],
        "core_skills": ["Python"],
        **profile,
    }


def test_a_role_at_an_employer_that_is_not_in_the_profile_is_a_violation():
    text = (
        "# Casey Chen\n\n## Experience\n### Backend Engineer, Acme Corp\n- Built APIs\n"
        "### Staff Engineer, Globex\n- Led"
    )
    check = check_generated_document("resume", text, _with_experience(), {"title": "T", "company": "Z"})

    assert len(check.violations) == 1 and "Globex" in check.violations[0]


def test_generic_headings_inside_experience_are_not_roles():
    text = "# Casey Chen\n\n## Experience\n### Backend Engineer, Acme Corp\n### Key Achievements\n- Built APIs"
    check = check_generated_document("resume", text, _with_experience(), {"title": "T", "company": "Z"})

    assert check.violations == []


def test_skills_missing_from_the_profile_are_one_warning():
    text = "# Casey Chen\n\n## Skills\n- Python, Haskell, Rust\n"
    check = check_generated_document("resume", text, _with_experience(), {"title": "T", "company": "Z"})

    assert check.violations == []
    assert len(check.warnings) == 1 and "Haskell" in check.warnings[0] and "Rust" in check.warnings[0]
    assert "Python" not in check.warnings[0]


def test_documents_that_point_at_gaps_or_hedge_are_rewritten():
    letter = LETTER.replace("I want to join", "Although I have not used Go, I want to join")
    hedged = _check("cover_letter", letter).violations
    assert len(hedged) == 1 and "although i" in hedged[0]
    assert any("familiar with" in v for v in _check("resume", "# Casey Chen\n\nFamiliar with Kubernetes.").violations)


def test_a_hedge_the_profile_itself_uses_is_allowed():
    profile = {**PROFILE, "core_skills": ["Python", "Familiar with Rust"]}
    assert _check("resume", "# Casey Chen\n\nFamiliar with Rust.", profile=profile).violations == []

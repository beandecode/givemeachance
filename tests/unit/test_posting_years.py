"""The years of experience read from a posting (made-up sentences only)."""

from __future__ import annotations

import pytest

from core.posting_years import YearsAsked, years_asked


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("You have 5+ years of experience building APIs.", YearsAsked(5, None)),
        ("5 or more years of professional software development.", YearsAsked(5, None)),
        ("At least 4 years working with cloud platforms.", YearsAsked(4, None)),
        ("A minimum of 3 years in a similar role.", YearsAsked(3, None)),
        ("Minimum 3 years hands-on experience with SQL.", YearsAsked(3, None)),
        ("3-5 years of relevant experience.", YearsAsked(3, 5)),
        ("3 to 5 years of experience in analytics.", YearsAsked(3, 5)),
        ("2–4 years' experience in data engineering.", YearsAsked(2, 4)),
        ("2-3 years’ experience in machine learning.", YearsAsked(2, 3)),
        ("Five years of experience in the field.", YearsAsked(5, None)),
        ("Five (5) years of related work experience.", YearsAsked(5, None)),
        ("7+ yrs exp with Java.", YearsAsked(7, None)),
        ("Experience: 3-7 years", YearsAsked(3, 7)),
        ("Requirements: 4+ years Python and dbt.", YearsAsked(4, None)),
        ("1+ year of experience with React.", YearsAsked(1, None)),
        ("4 to 7 years of full-time experience in DevOps.", YearsAsked(4, 7)),
        ("Bachelor's degree and 2 years of related experience.", YearsAsked(2, None)),
    ],
)
def test_reads_the_years_asked(text: str, expected: YearsAsked) -> None:
    assert years_asked(text) == expected


def test_highest_minimum_is_the_headline() -> None:
    text = "5+ years Python, 2+ years Spark. 3-4 years of experience with Airflow is a plus."
    assert years_asked(text) == YearsAsked(5, None)


def test_range_kept_with_its_minimum() -> None:
    text = "2+ years of SQL experience. 3-6 years of experience as a data engineer."
    assert years_asked(text) == YearsAsked(3, 6)


@pytest.mark.parametrize(
    "text",
    [
        "We are proud of 10 years of company history.",
        "Join a 401k plan after 2 years of service.",
        "Our firm has been over 20 years in business.",
        "Contracts of up to 3 years are available.",
        "Applicants must be 18 years of age or older.",
        "With 20+ years of proven success, we are the leading studio.",
        "For more than 90 years, our drive has kept us ahead.",
        "Founded 15 years ago in a garage.",
        "Recognised as a top employer for the last five years.",
        "Bonus milestones at 3, 5 and 10 years.",
        "Several years building machine learning systems.",
        "You must have lived here for 5 years.",
        "A 2 year fixed-term contract.",
        "",
    ],
)
def test_ignores_numbers_that_are_not_experience(text: str) -> None:
    assert years_asked(text) is None


def test_none_for_missing_text() -> None:
    assert years_asked(None) is None


def test_an_experience_requirement_wins_over_company_facts() -> None:
    text = "We have been in business for 30 years. You bring 3+ years of experience with Go."
    assert years_asked(text) == YearsAsked(3, None)

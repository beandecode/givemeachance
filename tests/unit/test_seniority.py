from datetime import date

import pytest

from core.seniority import default_levels, parse_years, title_allowed, title_level, years_from_experiences


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("Backend Engineer", "mid"),
        ("Software Developer II", "mid"),
        ("Junior Software Developer", "junior"),
        ("Software Engineering Intern", "junior"),
        ("Entry-Level Developer", "junior"),
        ("Senior Backend Engineer", "senior"),
        ("Sr. Data Engineer", "senior"),
        ("Tech Lead, Payments", "senior"),
        ("Staff Software Engineer", "staff_plus"),
        ("Principal Engineer", "staff_plus"),
        ("Senior Staff Engineer", "staff_plus"),
        ("Engineering Manager", "management"),
        ("Senior Engineering Manager", "management"),
        ("Head of Platform", "management"),
        ("Director of Engineering", "management"),
        ("Seniority Analyst", "mid"),  # a word that merely contains "senior"
        ("Account Manager", "mid"),  # manages accounts, cases or projects, not people
        ("Senior Project Manager", "senior"),
        ("Case Manager - Community Health", "mid"),
        ("General Manager", "management"),
        ("Director, Product Manager Group", "management"),
    ],
)
def test_title_level(title, level):
    assert title_level(title) == level


def test_no_selected_levels_means_every_title_is_allowed():
    assert title_allowed("Director of Engineering", []) is True
    assert title_allowed("Director of Engineering", None) is True


def test_titles_are_kept_only_for_the_selected_levels():
    levels = ["mid", "senior"]
    assert title_allowed("Backend Engineer", levels) is True
    assert title_allowed("Senior Backend Engineer", levels) is True
    assert title_allowed("Staff Engineer", levels) is False
    assert title_allowed("Engineering Manager", levels) is False
    assert title_allowed("Junior Developer", levels) is False


@pytest.mark.parametrize(
    ("text", "years"),
    [("5", 5.0), ("5+ years", 5.0), ("3-5 years", 4.0), ("2 to 4", 3.0), ("1.5", 1.5), ("unknown", None), ("", None)],
)
def test_parse_years(text, years):
    assert parse_years(text) == years


def test_years_from_the_earliest_experience_start():
    experiences = [{"start_date": "2022-05"}, {"duration": "2018-01 - 2021-12"}, {"start_date": "unknown"}]
    assert years_from_experiences(experiences, today=date(2026, 10, 25)) == 8.0
    assert years_from_experiences([{"start_date": "unknown"}], today=date(2026, 10, 25)) is None
    assert years_from_experiences("nope") is None


def test_internships_and_volunteering_do_not_count_as_years_of_work():
    experiences = [
        {"start_date": "2024-06", "employment_type": "Full-time"},
        {"start_date": "2019-05", "employment_type": "Internship"},
        {"start_date": "2018-09", "title": "Software Developer (co-op)"},
        {"start_date": "2017-01", "employment_type": "Volunteer"},
    ]
    assert years_from_experiences(experiences, today=date(2026, 10, 25)) == 2.0


@pytest.mark.parametrize(
    ("years", "levels"),
    [
        ("1", ["junior", "mid"]),
        ("4", ["junior", "mid", "senior"]),
        ("8", ["mid", "senior", "staff_plus"]),
        ("12", ["mid", "senior", "staff_plus", "management"]),
        ("unknown", []),
    ],
)
def test_default_levels_follow_years_of_experience(years, levels):
    assert default_levels({"identity": {"years_experience": years}}, today=date(2026, 10, 25)) == levels


def test_default_levels_fall_back_to_the_experience_dates_and_then_to_all_levels():
    profile = {"identity": {}, "experiences": [{"start_date": "2023-01"}]}
    assert default_levels(profile, today=date(2026, 10, 25)) == ["junior", "mid", "senior"]
    assert default_levels({"identity": {}, "experiences": []}) == []

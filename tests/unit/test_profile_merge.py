"""Building or rebuilding a profile never loses what the candidate gave, and answers land where they belong."""

import io

import pytest
from docx import Document

from core.profile_input_service import ProfileInputError, docx_text
from core.profile_synthesis import _normalize_master_profile

PREVIOUS = {
    "identity": {"name": "Casey Chen", "current_title": "Backend Engineer", "location": "Toronto, ON"},
    "experiences": [
        {
            "title": "Backend Engineer",
            "company": "TrueNorth",
            "start_date": "2022-05",
            "end_date": "present",
            "highlights": ["Owns the reporting API"],
            "achievements": [],
        },
        {
            "title": "Developer",
            "company": "HarborStack",
            "start_date": "unknown",
            "end_date": "unknown",
            "highlights": ["Built REST integrations"],
            "achievements": [],
        },
    ],
    "projects": [{"name": "Job queue", "summary": "Postgres jobs", "impact": []}],
    "certifications": ["AWS Developer - Associate (2023)"],
    "languages": ["English", "Mandarin"],
    "career_highlights": ["Cut AWS spend by 28%"],
}


def _rebuild(model_output: dict, answers: dict, previous: dict | None = PREVIOUS, **details) -> dict:
    bundle = {"resume_text": "", "user_details": details, "previous_profile": previous, "supplement_answers": answers}
    return _normalize_master_profile(model_output, bundle, [], "m")


def test_an_answer_about_the_second_role_goes_to_the_second_role():
    model = {"experiences": [dict(e) for e in PREVIOUS["experiences"]]}
    profile = _rebuild(
        model,
        {
            "experiences[1].achievements": "Cut failed callbacks by 70%",
            "experiences[1].start_date": "2020-01 - 2022-04",
        },
    )
    first, second = profile["experiences"]
    assert second["achievements"] == ["Cut failed callbacks by 70%"]
    assert (second["start_date"], second["end_date"]) == ("2020-01", "2022-04")
    assert first["achievements"] == [] and first["start_date"] == "2022-05"


def test_an_answer_follows_its_role_when_the_model_reorders_them():
    model = {"experiences": [dict(PREVIOUS["experiences"][1]), dict(PREVIOUS["experiences"][0])]}
    profile = _rebuild(model, {"experiences[1].achievements": "Cut failed callbacks by 70%"})
    harbor = next(e for e in profile["experiences"] if e["company"] == "HarborStack")
    assert harbor["achievements"] == ["Cut failed callbacks by 70%"]


def test_a_project_answer_becomes_impact():
    profile = _rebuild({"projects": [dict(PREVIOUS["projects"][0])]}, {"projects[0].impact": "Used by two teams"})
    assert profile["projects"][0]["impact"] == ["Used by two teams"]


def test_a_rebuild_puts_back_everything_the_model_dropped():
    profile = _rebuild({"experiences": [{"title": "Backend Engineer", "company": "TrueNorth"}]}, {})
    assert [e["company"] for e in profile["experiences"]] == ["TrueNorth", "HarborStack"]
    assert profile["experiences"][0]["highlights"] == ["Owns the reporting API"]
    assert profile["experiences"][0]["start_date"] == "2022-05"
    assert profile["projects"][0]["name"] == "Job queue"
    assert profile["certifications"] == ["AWS Developer - Associate (2023)"]
    assert profile["languages"] == ["English", "Mandarin"]
    assert profile["career_highlights"] == ["Cut AWS spend by 28%"]
    assert profile["identity"]["current_title"] == "Backend Engineer"


def test_what_the_candidate_typed_wins_over_the_model():
    model = {
        "identity": {"current_title": "Software Engineer", "location": "Vancouver"},
        "preferences": {"target_roles": ["Software Engineer"]},
    }
    profile = _rebuild(model, {}, previous=None, current_title="Data Engineer", target_roles=["Data Engineer"])
    assert profile["identity"]["current_title"] == "Data Engineer"
    assert profile["identity"]["location"] == "Vancouver"
    assert profile["preferences"]["target_roles"] == ["Data Engineer"]


def test_education_and_certification_records_keep_every_part():
    model = {
        "education": [{"degree": "BScN", "school": "TMU", "years": "2017 - 2021", "honors": "Dean's list"}],
        "certifications": [{"name": "Registered Nurse", "issuer": "CNO", "year": "2021"}],
    }
    profile = _rebuild(model, {}, previous=None)
    assert profile["education"] == ["BScN - TMU - 2017 - 2021 - Dean's list"]
    assert profile["certifications"] == ["Registered Nurse - CNO - 2021"]


def _docx(*paragraphs: str, table: list[list[str]] | None = None) -> bytes:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, text in enumerate(row):
                grid.cell(r, c).text = text
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_a_word_resume_is_read_as_text_including_tables():
    text = docx_text(_docx("Morgan Patel", "Registered Nurse", table=[["2021 - present", "Lakeshore General"]]))
    assert text.splitlines() == ["Morgan Patel", "Registered Nurse", "2021 - present | Lakeshore General"]


def test_a_broken_word_file_is_a_clear_error():
    with pytest.raises(ProfileInputError, match="Word file"):
        docx_text(b"not a zip")


def test_a_degree_or_credential_written_with_commas_stays_one_entry():
    model = {
        "education": ["BScN, Toronto Metropolitan University (2017 - 2021), Dean's list"],
        "certifications": ["BLS, Heart and Stroke Foundation, 2024"],
    }
    profile = _rebuild(model, {}, previous=None)
    assert profile["education"] == ["BScN, Toronto Metropolitan University (2017 - 2021), Dean's list"]
    assert profile["certifications"] == ["BLS, Heart and Stroke Foundation, 2024"]


def test_a_bullet_copied_into_both_lists_is_kept_once():
    model = {
        "experiences": [
            {
                "title": "Dev",
                "company": "Acme",
                "highlights": ["Cut latency by 76%."],
                "achievements": ["Cut latency by 76%", "Won the hackathon"],
            }
        ]
    }
    entry = _rebuild(model, {}, previous=None)["experiences"][0]
    assert entry["highlights"] == ["Cut latency by 76%."] and entry["achievements"] == ["Won the hackathon"]

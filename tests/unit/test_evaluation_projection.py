import json

from core.evaluation_profile import evaluation_is_current, evaluation_projection, profile_fingerprint

PROFILE = {
    "identity": {
        "name": "Casey Chen",
        "contact": {"email": "casey@example.com", "phone": "+1-647-555-0137"},
        "location": "Ottawa, ON",
        "current_title": "Software Engineer",
        "years_experience": "4",
    },
    "profile_summary": "Backend engineer focused on reliable APIs.",
    "core_skills": ["Python", "SQL", "Flask"],
    "skill_matrix": {"cloud": ["AWS"]},
    "experiences": [
        {
            "title": f"Engineer {n}",
            "company": f"Company {n}",
            "duration": "2020 - 2022",
            "highlights": ["a", "b", "c", "d", "e"],
            "achievements": ["x", "y", "z", "w"],
            "tech_stack": ["Go"],
        }
        for n in range(10)
    ],
    "projects": [
        {"name": f"Project {n}", "summary": "unknown", "impact": ["i1", "i2", "i3"], "tech_stack": ["Rust"]}
        for n in range(5)
    ],
    "education": [{"degree": "BSc", "school": "Uni"}],
    "preferences": {
        "target_roles": ["Backend Engineer", "unknown"],
        "preferred_locations": ["Toronto"],
        "work_authorization": "Canada PR",
    },
}


def test_the_scorer_sees_level_preferences_projects_and_more_experience():
    resume = evaluation_projection(PROFILE)

    assert resume["candidate"] == {
        "current_title": "Software Engineer",
        "years_experience": "4",
        "location": "Ottawa, ON",
        "summary": "Backend engineer focused on reliable APIs.",
        "work_authorization": "Canada PR",
        "target_roles": ["Backend Engineer"],
        "preferred_locations": ["Toronto"],
    }
    assert len(resume["experience"]) == 8
    assert len(resume["experience"][0]["responsibilities"]) == 9  # up to 6 highlights + 4 achievements
    assert [p["name"] for p in resume["projects"]] == ["Project 0", "Project 1", "Project 2"]
    assert resume["projects"][0] == {"name": "Project 0", "summary": "", "impact": ["i1", "i2"], "tech_stack": ["Rust"]}
    assert resume["education"] == ["BSc - Uni"]


def test_the_mock_evaluator_still_finds_the_skills():
    assert {"Python", "SQL", "Flask", "AWS"} <= set(evaluation_projection(PROFILE)["skills"]["core"])


def test_name_email_and_phone_never_reach_the_provider():
    payload = json.dumps(evaluation_projection(PROFILE))

    for private in ("Casey", "casey@example.com", "647-555-0137"):
        assert private not in payload


def test_fingerprint_ignores_contact_details_but_not_skills_or_level():
    changed_name = {**PROFILE, "identity": {**PROFILE["identity"], "name": "Casey Chen-Smith"}}
    changed_phone = {**PROFILE, "identity": {**PROFILE["identity"], "contact": {"phone": "+1-613-555-0100"}}}
    more_skills = {**PROFILE, "core_skills": [*PROFILE["core_skills"], "Rust"]}
    more_years = {**PROFILE, "identity": {**PROFILE["identity"], "years_experience": "9"}}

    base = profile_fingerprint(PROFILE)

    assert profile_fingerprint(changed_name) == base
    assert profile_fingerprint(changed_phone) == base
    assert profile_fingerprint(more_skills) != base
    assert profile_fingerprint(more_years) != base


def _profile_row(profile_id, master):
    return {"id": profile_id, "master_profile_json": json.dumps(master)}


def test_an_evaluation_stays_current_across_edits_the_scorer_cannot_see(tmp_path):
    import sqlite3

    from core.db import init_db

    db = tmp_path / "fp.db"
    init_db(str(db))
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO users (username, password_hash, created_at, is_active) VALUES ('u', 'x', 'now', 1)")
    old_master = PROFILE
    renamed = {**PROFILE, "identity": {**PROFILE["identity"], "name": "Casey Chen-Smith"}}
    reskilled = {**PROFILE, "core_skills": ["Rust", "Go", "C"]}
    for n, master in enumerate((old_master, renamed, reskilled), start=1):
        conn.execute(
            "INSERT INTO candidate_profiles (id, user_id, profile_version, source_bundle_json, master_profile_json,"
            " model_name, created_at, review_status) VALUES (?, 1, ?, '{}', ?, 'm', 'now', 'approved')",
            (n, n, json.dumps(master)),
        )
    evaluation_of_v1 = {"source_profile_id": 1, "source_profile_fingerprint": None}  # evaluated before fingerprints

    assert evaluation_is_current(conn, evaluation_of_v1, _profile_row(1, old_master)) is True
    assert evaluation_is_current(conn, evaluation_of_v1, _profile_row(2, renamed)) is True
    assert evaluation_is_current(conn, evaluation_of_v1, _profile_row(3, reskilled)) is False
    stored = {"source_profile_id": 1, "source_profile_fingerprint": profile_fingerprint(old_master)}
    assert evaluation_is_current(conn, stored, _profile_row(2, renamed)) is True
    assert evaluation_is_current(conn, {"source_profile_id": None, "source_profile_fingerprint": None}, None) is True
    assert evaluation_is_current(conn, evaluation_of_v1, None) is False
    conn.close()


def test_the_scorer_sees_licences_spoken_languages_and_highlights():
    profile = {
        "certifications": ["Registered Nurse (CNO)", {"name": "BLS"}],
        "languages": ["English", "French"],
        "career_highlights": ["Charge nurse of the year 2024"],
    }
    resume = evaluation_projection(profile)
    assert resume["certifications_and_licences"] == ["Registered Nurse (CNO)", "BLS"]
    assert resume["candidate"]["spoken_languages"] == ["English", "French"]
    assert resume["candidate"]["highlights"] == ["Charge nurse of the year 2024"]

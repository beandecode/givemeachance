from core.parsing import is_core_high_field
from core.request_normalization import (
    apply_supplement_answer,
    normalize_user_details,
    parse_json_dict,
    parse_list_input,
    parse_optional_bool,
    parse_text_list,
)


def test_parse_optional_bool_variants():
    assert parse_optional_bool(True) is True
    assert parse_optional_bool(False) is False
    assert parse_optional_bool("YES") is True
    assert parse_optional_bool("no") is False
    assert parse_optional_bool("unknown") is None


def test_parse_list_and_text_helpers():
    assert parse_list_input("a,b\nc") == ["a", "b", "c"]
    assert parse_list_input([" x ", "", "y"]) == ["x", "y"]
    assert parse_text_list('["a", "b", "c"]', limit=2) == ["a", "b"]
    assert parse_text_list("line1\nline2", limit=4) == ["line1", "line2"]


def test_parse_json_dict_and_normalize_user_details():
    assert parse_json_dict('{"k": "v"}') == {"k": "v"}
    assert parse_json_dict("not-json") == {}

    normalized = normalize_user_details(
        {
            "candidate_name": "  Alex  ",
            "target_roles": "Backend Engineer,Platform Engineer",
            "preferred_locations": ["Toronto", "  Remote  "],
            "links": "https://a\nhttps://b",
            "supplement_overrides": {"core_skills": "Python"},
        }
    )

    assert normalized["candidate_name"] == "Alex"
    assert normalized["target_roles"] == ["Backend Engineer", "Platform Engineer"]
    assert normalized["preferred_locations"] == ["Toronto", "Remote"]
    assert normalized["links"] == ["https://a", "https://b"]
    assert normalized["supplement_overrides"] == {"core_skills": "Python"}


def test_apply_supplement_answer_and_high_priority_field():
    user_details = normalize_user_details({})
    apply_supplement_answer(user_details, "identity.name", "Taylor")
    apply_supplement_answer(user_details, "preferences.target_roles", "Backend Engineer,API Engineer")

    assert user_details["candidate_name"] == "Taylor"
    assert user_details["target_roles"] == ["Backend Engineer", "API Engineer"]
    assert user_details["supplement_overrides"]["identity.name"] == "Taylor"

    assert is_core_high_field("identity.name") is True
    assert is_core_high_field("experiences") is True
    assert is_core_high_field("experiences.0.title") is False
    assert is_core_high_field("experiences[0].achievements") is False
    assert is_core_high_field("languages") is False

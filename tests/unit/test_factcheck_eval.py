"""The fact-check test (scripts/factcheck_eval.py): scoring on made-up audit output, and the committed cases."""

from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("factcheck_script", ROOT / "scripts" / "factcheck_eval.py")
assert spec and spec.loader
factcheck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(factcheck)

CASE = {
    "id": "x1",
    "kind": "resume",
    "text": "Engineering Manager at Northwind; latency fell to 120 ms",
    "planted": [
        {"type": "employer", "keywords": ["northwind"]},
        {"type": "number", "keywords": ["120 ms"]},
    ],
}
OTHER = {"id": "x2", "kind": "cover_letter", "text": "Senior", "planted": [{"type": "title", "keywords": ["senior"]}]}


def _claim(text: str, status: str) -> dict:
    return {"text": text, "status": status, "profile_path": "", "quote": ""}


def test_planted_claim_is_caught_only_when_marked_unsupported():
    claims = [_claim("Works at NORTHWIND Logistics", "unsupported"), _claim("p95 latency 120ms", "supported")]
    scored = factcheck.score_case(CASE, claims)
    assert scored["caught"] == [True, False]  # case-insensitive; spaces ignored, but "supported" is a miss
    assert scored["others"] == []


def test_evaluate_counts_types_false_flags_and_skips_errors():
    results = {
        "x1": {
            "claims": [
                _claim("Software Developer at Northwind", "unsupported"),
                _claim("Latency fell to 120 ms", "unsupported"),
                _claim("Five years of experience", "supported"),
                _claim("Mentors two juniors", "unsupported"),  # matches no planted claim: a false flag
                _claim("Clear communicator", "inferred"),
            ],
            "seconds": 3.0,
        },
        "x2": {"claims": [_claim("Senior Backend Engineer", "supported")], "seconds": 5.0},
        "x3": {"error": "ProviderOutputInvalid: no claims"},
    }
    result = factcheck.evaluate([CASE, OTHER, {"id": "x3", "planted": []}], results)
    assert result["documents"] == 2
    assert (result["caught"], result["planted"]) == (2, 3)
    assert result["by_type"] == {"employer": (1, 1), "number": (1, 1), "title": (0, 1)}
    assert result["all_caught"] == 1
    assert (result["false_flags"], result["other_claims"]) == (1, 3)
    assert result["false_flag_examples"] == [{"id": "x1", "text": "Mentors two juniors"}]
    assert result["median_seconds"] == 5.0
    table = factcheck.format_report("model-x", result, {"input_tokens": 10, "output_tokens": 2})
    assert "| Planted claims caught | 2 of 3 (67%) |" in table
    assert "10 in, 2 out" in table


def test_report_has_one_table_per_set_with_its_own_tokens():
    data = {
        "results": {"r01": {"claims": [_claim("Software Developer at Northwind Logistics", "unsupported")]}},
        "usage_by_set": {"blunt": {"input_tokens": 7, "output_tokens": 3}},
    }
    text = factcheck.report_sets("model-x", data)
    assert "model-x, blunt set: 1 documents audited" in text
    assert "7 in, 3 out" in text
    assert "subtle set" not in text  # no subtle results yet
    assert factcheck.set_of("sc01") == "subtle" and factcheck.set_of("r01") == "blunt"


def _profile_text() -> str:
    return (ROOT / "data" / "mock" / "demo_profile.json").read_text().lower()


def _check_case(case: dict, profile: str) -> None:
    """Every keyword is in its document. It is absent from the profile, unless the planted claim is a real detail in
    the wrong place (marked in_profile): then the keyword must occur exactly once in the document and be a phrase of
    two or more words or a year, so it still points at that one claim."""
    assert 1 <= len(case["planted"]) <= 2, case["id"]
    text = case["text"].lower()
    for item in case["planted"]:
        for keyword in item["keywords"]:
            assert keyword == keyword.lower(), keyword
            assert keyword in text, (case["id"], keyword)
            in_profile = keyword in profile or factcheck.normalize(keyword) in factcheck.normalize(profile)
            if item.get("in_profile"):
                assert in_profile, (case["id"], keyword, "marked in_profile but absent: drop the mark")
                assert text.count(keyword) == 1, (case["id"], keyword)
                assert " " in keyword or (keyword.isdigit() and len(keyword) == 4), (case["id"], keyword)
            else:
                assert not in_profile, (case["id"], keyword)


def test_blunt_cases_are_consistent_with_the_profile():
    profile, cases = _profile_text(), factcheck.BLUNT_CASES
    assert len(cases) == 20
    assert Counter(case["kind"] for case in cases) == {"resume": 10, "cover_letter": 10}
    planted = [item for case in cases for item in case["planted"]]
    assert 28 <= len(planted) <= 34
    assert {item["type"] for item in planted} == set(factcheck.TYPES)
    assert not any(item.get("in_profile") for item in planted)
    for case in cases:
        _check_case(case, profile)


def test_subtle_cases_are_consistent_with_the_profile():
    profile, cases = _profile_text(), factcheck.SUBTLE_CASES
    assert len(cases) == 12
    assert Counter(case["kind"] for case in cases) == {"resume": 6, "cover_letter": 6}
    planted = [item for case in cases for item in case["planted"]]
    assert 18 <= len(planted) <= 24
    assert {item["type"] for item in planted} == set(factcheck.SUBTLE_TYPES)
    for case in cases:
        _check_case(case, profile)


def test_case_ids_are_unique_across_sets():
    ids = [case["id"] for case in factcheck.CASES]
    assert len(ids) == len(set(ids)) == 32

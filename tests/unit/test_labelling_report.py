"""The match-quality report (scripts/labelling.py report): made-up postings only, never the real labelled set."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "labelling.py"
spec = importlib.util.spec_from_file_location("labelling_script", SCRIPT)
assert spec and spec.loader
labelling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labelling)


def _item(score: int, seniority: int) -> dict:
    return {"score": score, "dimensions": {"seniority_match": seniority}, "seconds": 2.0}


LABELS = {
    "a": {"decision": "apply", "level": "fits"},
    "b": {"decision": "apply", "level": "fits"},
    "c": {"decision": "skip", "level": "too_senior"},
    "d": {"decision": "maybe", "level": "too_senior"},
    "e": {"decision": "skip", "level": "unsure"},
}
RESULTS = {
    "a": _item(80, 90),
    "b": _item(60, 40),
    "c": _item(75, 40),  # ties with b on level, beats b on score
    "d": _item(30, 10),
    "e": _item(20, 50),
    "f": _item(99, 99),  # not labelled: ignored
}


def test_pair_agreement_counts_ties_as_half():
    assert labelling.pair_agreement([3, 1], [2]) == 0.5
    assert labelling.pair_agreement([5], [1, 2]) == 1.0
    assert math.isnan(labelling.pair_agreement([], [1]))


def test_interval_is_repeatable_and_brackets_the_estimate():
    better, worse = [9.0, 8.0, 7.0, 3.0, 6.0], [2.0, 4.0, 8.0, 1.0]
    first = labelling.agreement_interval(better, worse)
    assert first == labelling.agreement_interval(better, worse)
    low, high = first
    assert 0 <= low <= labelling.pair_agreement(better, worse) <= high <= 1


def test_evaluate_scores_reads_the_readme_measures():
    result = labelling.evaluate_scores(LABELS, RESULTS)
    assert result["scored"] == 5  # the unlabelled posting is left out
    # fits {90, 40} against too_senior {40, 10}: 3.5 of 4 pairs
    assert result["level"] == 0.875
    # apply {80, 60} against skip {75, 20}: 3 of 4 pairs (60 sits below 75)
    assert result["decision"] == 0.75
    assert (result["fits_in_deck"], result["fits"]) == (1, 2)
    assert result["deck"] == 2 and result["skips_in_deck"] == 1


def test_report_text_has_the_table_rows():
    text = labelling.format_report("model-x", labelling.evaluate_scores(LABELS, RESULTS), {"input_tokens": 5})
    assert "model-x: 5 labelled postings scored" in text
    assert "| 0.88 |" in text and "1 of 2" in text and "5 in, 0 out" in text


def test_states_years():
    assert labelling.states_years("Minimum 3+ years of experience")
    assert labelling.states_years("5-7 years in data science")
    assert not labelling.states_years("Join our team of experts")


def test_cost_per_100_uses_the_counted_tokens():
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000}
    # 10 postings used 1M in at $0.30 and 0.1M out at $2.50 = $0.55, so $5.50 per 100
    assert round(labelling.cost_per_100("gemini-3.5-flash-lite", usage, 10), 2) == 5.5
    assert labelling.cost_per_100("unknown-model", usage, 10) is None
    assert labelling.cost_per_100("gemini-3.5-flash-lite", None, 10) is None

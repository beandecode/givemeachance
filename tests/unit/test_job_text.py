import pytest

from core.job_text import is_description_snippet

FULL = "Build and run backend services. " * 40


@pytest.mark.parametrize(
    ("source", "description", "expected"),
    [
        ("adzuna", "x" * 499 + "…", True),
        ("adzuna", "x" * 497 + "...", True),
        ("adzuna", "A short posting that really ends here.", False),
        ("adzuna", FULL, False),
        ("adzuna", FULL + "…", False),  # too long to be the board's preview
        ("manual", "x" * 100 + "…", False),  # only job-board previews count
        ("mock_adzuna", "x…", False),
    ],
)
def test_is_description_snippet(source, description, expected):
    assert is_description_snippet(source, description) is expected

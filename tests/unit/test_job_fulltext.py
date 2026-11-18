import json

import pytest

from core.job_fulltext import description_from_page, fetch_full_description

FULL = "<p>We are hiring a data scientist.</p><ul><li>3+ years of Python &amp; SQL</li><li>Build models</li></ul>" * 5
PREVIEW = "We are hiring a data scientist. 3+ years of Python & SQL Build models…"


def page(*items: object) -> str:
    scripts = "".join(f'<script type="application/ld+json">{json.dumps(item)}</script>' for item in items)
    return f"<html><head>{scripts}</head><body>ad</body></html>"


def test_reads_the_job_posting_as_plain_text_with_line_breaks():
    text = description_from_page(page({"@type": "Organization"}, {"@type": "JobPosting", "description": FULL}))
    assert text is not None
    assert "3+ years of Python & SQL" in text and "<" not in text
    assert "\n" in text
    assert description_from_page(page({"@graph": [{"@type": "JobPosting", "description": FULL}]})) == text
    assert description_from_page("<html>no structured data</html>") is None
    assert description_from_page('<script type="application/ld+json">{broken</script>') is None


@pytest.mark.parametrize(
    ("url", "final", "body", "expected"),
    [
        (
            "https://www.adzuna.ca/details/1",
            "https://www.adzuna.ca/details/1",
            page({"@type": "JobPosting", "description": FULL}),
            True,
        ),
        # only the job board's own pages are read
        (
            "https://example.com/job/1",
            "https://example.com/job/1",
            page({"@type": "JobPosting", "description": FULL}),
            False,
        ),
        (
            "https://www.adzuna.ca/land/1",
            "https://careers.example.com/1",
            page({"@type": "JobPosting", "description": FULL}),
            False,
        ),
        # a page whose text is no longer than the preview does not replace it
        (
            "https://www.adzuna.ca/details/1",
            "https://www.adzuna.ca/details/1",
            page({"@type": "JobPosting", "description": "short"}),
            False,
        ),
        ("https://www.adzuna.ca/details/1", "https://www.adzuna.ca/details/1", "<html></html>", False),
    ],
)
def test_fetches_only_full_text_from_the_job_board(url, final, body, expected):
    text = fetch_full_description(url, PREVIEW, fetch=lambda _: (final, body))
    assert (text is not None) is expected
    if expected:
        assert len(text) > len(PREVIEW)


def test_network_errors_leave_the_preview():
    def broken(_url):
        raise OSError("connection reset")

    assert fetch_full_description("https://www.adzuna.ca/details/1", PREVIEW, fetch=broken) is None
    assert fetch_full_description("", PREVIEW) is None

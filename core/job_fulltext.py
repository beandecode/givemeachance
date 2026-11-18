"""Full job descriptions for postings the job board's search API returns only as a preview.

Adzuna's search API cuts each description to a short preview and has no endpoint for one ad. Its detail page (the
ad's `redirect_url`) carries the whole posting as schema.org `JobPosting` data, the same markup job sites publish for
search engines, so the full text is read from there: one page per job, only on the job board's own site, no AI call.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from core.job_text import MIN_FULL_DESCRIPTION_LENGTH
from core.logging_setup import log_provider_call

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_LENGTH = 10_000
TIMEOUT_SECONDS = 15
MAX_PAGE_BYTES = 2_000_000
_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
_LD_JSON = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)

Fetch = Callable[[str], tuple[str, str]]  # url -> (final url, page text)


def _job_board_host(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "adzuna.com" or ".adzuna." in f".{host}" or host.startswith("adzuna.")


def _fetch(url: str) -> tuple[str, str]:
    request = Request(url, headers={"User-Agent": _AGENT, "Accept-Language": "en"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (https job-board URL, host checked)
        return response.geturl(), response.read(MAX_PAGE_BYTES).decode("utf-8", "replace")


def description_from_page(page: str) -> str | None:
    """The description of the first schema.org JobPosting on an HTML page, as plain text."""
    for block in _LD_JSON.findall(page):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                text = re.sub(r"<(?:br|/p|/li|/h\d)[^>]*>", "\n", str(item.get("description", "")), flags=re.I)
                text = html.unescape(re.sub(r"<[^>]+>", " ", text))
                text = "\n".join(re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines())
                text = re.sub(r"\n{3,}", "\n\n", text).strip()
                return text[:MAX_DESCRIPTION_LENGTH] or None
    return None


def fetch_full_description(url: str, preview: str = "", fetch: Fetch = _fetch) -> str | None:
    """The full text of a job-board posting, or None when the page is unavailable or not longer than the preview."""
    if not url or not _job_board_host(url):
        return None
    started = time.monotonic()
    status: object = "error"
    try:
        final_url, page = fetch(url)
        if not _job_board_host(final_url):
            status = "left the job board"
            return None
        text = description_from_page(page)
        if text is None or len(text) < MIN_FULL_DESCRIPTION_LENGTH or len(text) <= len(preview.rstrip(" .…")):
            status = "no full description"
            return None
        status = "ok"
        return text
    except (OSError, ValueError) as error:
        status = f"{type(error).__name__}: {error}"[:80]
        return None
    finally:
        log_provider_call(logger, "adzuna", "detail_page", 1, started, status)

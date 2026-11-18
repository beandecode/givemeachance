"""Hard filters on a posting, applied before it is stored or scored (ADR-017).

Everything here reads the posting's own text, so it is a heuristic: it never drops a posting that does not say
something plainly (an unknown work mode or a missing salary passes). Adzuna returns only a short preview of each
posting, so a requirement that sits further down the text is not seen; the scorer still judges those.
"""

from __future__ import annotations

import re

from core.schemas import JobRecord, JobSearchConfig, WorkMode

_WORK_MODE_PATTERNS: tuple[tuple[WorkMode, re.Pattern[str]], ...] = (
    ("hybrid", re.compile(r"\bhybrid\b", re.IGNORECASE)),
    ("remote", re.compile(r"\b(?:remote|work from home|wfh|fully distributed)\b", re.IGNORECASE)),
    ("onsite", re.compile(r"\bon[- ]?site\b|\bin[- ](?:the )?office\b|\bin[- ]person\b", re.IGNORECASE)),
)
_KNOCKOUT_PATTERNS: dict[str, re.Pattern[str]] = {
    "security_clearance": re.compile(
        r"security clearance|secret clearance|top secret|ts/sci|clearance (?:is )?required|reliability status",
        re.IGNORECASE,
    ),
    "citizenship_required": re.compile(
        r"must be an? (?:u\.?s\.?|canadian|uk|eu)?\s*citizen|citizenship (?:is )?required|"
        r"(?:u\.?s\.?|canadian) citizens? only|permanent residents? only",
        re.IGNORECASE,
    ),
    "no_sponsorship": re.compile(
        r"(?:no|not|unable to|cannot|can't|won't|will not|do not|does not) (?:\w+ ){0,3}sponsor|"
        r"sponsorship (?:is )?(?:not|unavailable)",
        re.IGNORECASE,
    ),
}

FILTER_KEYS = ("salary", "title_word", "work_mode", "knockout")


def classify_work_mode(job: JobRecord) -> WorkMode | None:
    """The work mode the posting names (hybrid wins over remote), or None when it names none."""
    text = f"{job.title} {job.location} {job.description}"
    for mode, pattern in _WORK_MODE_PATTERNS:
        if pattern.search(text):
            return mode
    return None


def has_filters(config: JobSearchConfig) -> bool:
    return bool(
        config.work_modes or config.exclude_title_words or config.knockouts or config.adzuna.salary_min is not None
    )


def filter_reason(job: JobRecord, config: JobSearchConfig) -> str | None:
    """The first filter that drops this posting (one of FILTER_KEYS), or None when it passes all of them."""
    minimum = config.adzuna.salary_min
    if minimum is not None and job.salary_max is not None and job.salary_max < minimum:
        return "salary"
    title = job.title.casefold()
    if any(re.search(rf"(?<!\w){re.escape(word.casefold())}(?!\w)", title) for word in config.exclude_title_words):
        return "title_word"
    if config.work_modes:
        mode = classify_work_mode(job)
        if mode is not None and mode not in config.work_modes:
            return "work_mode"
    text = f"{job.title} {job.description}"
    if any(_KNOCKOUT_PATTERNS[name].search(text) for name in config.knockouts):
        return "knockout"
    return None

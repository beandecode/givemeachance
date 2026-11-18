"""The years of experience a job posting asks for, read from its text with fixed rules (no AI).

Shown next to the match score as a separate fact ("Asks for 5+ years"): the score describes fit, the level
is what the posting states. Where a posting lists several requirements ("5+ years Python, 2+ years Spark"),
the highest minimum is the headline. Numbers that are not about experience (company history, ages, benefits
that start after a period, contract lengths) are ignored; nothing credible returns None.
"""

from __future__ import annotations

import re
from typing import NamedTuple

_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
# A number: digits or a spelled-out word, optionally followed by the digits in brackets ("five (5)").
_NUM = r"(?:\d{1,2}|" + "|".join(_WORDS) + r")(?:\s*\(\d{1,2}\))?"
_DASH = r"\s*(?:-|–|—|to)\s*"
_UNIT = r"\s*(?:years?|yrs?)\b['’]?"

_MENTION = re.compile(
    r"(?P<lead>\b(?:at\s+least|a\s+minimum\s+of|minimum\s+of|minimum|min\.?|up\s+to|over|more\s+than|after|"
    r"within))?\s*"
    rf"\b(?P<low>{_NUM})"
    # A range: "3-5", "3 to 5", or "3 5" where the dash was lost when the page was read.
    rf"(?:(?:{_DASH}|[ \t]+(?=\d))(?P<high>{_NUM}))?"
    rf"\s*(?P<plus>\+|\s+or\s+more|\s+or\s+greater)?{_UNIT}",
    re.IGNORECASE,
)

# Words shortly after the number that make it a statement about experience.
_EXPERIENCE_AFTER = re.compile(
    r"^[^.;:\n]{0,60}?\b(?:experience[sd]?|exp\b|work(?:ing)?\b|background|professional(?:ly)?|"
    r"in\s+(?:a|an|the)\s+(?:similar|related|comparable|relevant)|in\s+the\s+field|in\s+industry|"
    r"industry|hands[\s-]on|track\s+record|post[\s-]qualification|in\s+(?:a|an)\s+\w+(?:\s+\w+)?\s+(?:role|position)|"
    r"as\s+(?:a|an)\s+\w+)",
    re.IGNORECASE,
)
# Words just before the number that frame it as experience ("Experience: 3-5 years").
_EXPERIENCE_BEFORE = re.compile(r"\bexperience\b[^.;\n]{0,25}$", re.IGNORECASE)
# Words right after the unit that rule the number out, whatever else is around it.
_NOT_EXPERIENCE_AFTER = re.compile(
    r"^\s*(?:of\s+age|old|of\s+(?:company\s+)?history|in\s+business|in\s+operation|ago|of\s+service|"
    r"of\s+(?:continuous\s+)?employment\s+with\s+us|warranty|contract|fixed[\s-]term|tenure|"
    r"of\s+(?:growth|success|innovation|excellence|heritage|trading))\b",
    re.IGNORECASE,
)
_NOT_EXPERIENCE_NEAR = re.compile(
    r"\b(?:company|founded|established|history|business|anniversary|age|aged|older|401k|401\(k\)|pension|vest|"
    r"vesting|sabbatical|bonus|contract|fixed[\s-]term|visa|residency|resident|citizen|apprenticeship|"
    r"program(?:me)?|course|warranty)\b",
    re.IGNORECASE,
)
# The employer talking about itself ("20+ years of proven success, we are the leading ...").
_COMPANY_VOICE = re.compile(
    r"\b(?:we|we['’]re|our|us|success|leader|leading|serving|served|trusted|customers|clients)\b", re.IGNORECASE
)
# Lead words that never introduce a requirement ("after 2 years", "up to 3 years", "within 5 years").
_NEGATIVE_LEADS = {"up to", "after", "within"}
_REQUIRING_LEADS = {"at least", "minimum", "minimum of", "a minimum of", "min.", "min"}

_MAX_YEARS = 15


class YearsAsked(NamedTuple):
    minimum: int
    maximum: int | None


def _number(text: str | None) -> int | None:
    if not text:
        return None
    head = re.match(r"\d{1,2}|[a-z]+", text.strip().lower())
    if head is None:
        return None
    word = head.group(0)
    return int(word) if word.isdigit() else _WORDS.get(word)


def _lead(match: re.Match[str]) -> str:
    return " ".join((match.group("lead") or "").lower().split())


def _credible(text: str, match: re.Match[str]) -> bool:
    after = text[match.end() : match.end() + 80]
    before = text[max(0, match.start() - 40) : match.start()]
    lead = _lead(match)
    if lead in _NEGATIVE_LEADS or _NOT_EXPERIENCE_AFTER.match(after):
        return False
    window_after = re.split(r"[.;\n]", after, maxsplit=1)[0]
    if _NOT_EXPERIENCE_NEAR.search(window_after[:30]):
        return False
    experience = _EXPERIENCE_AFTER.match(after)
    if experience is not None:
        return not _COMPANY_VOICE.search(after[: experience.end()])
    if _EXPERIENCE_BEFORE.search(before):
        return True
    # Without an experience word, only a clearly stated requirement counts ("5+ years Python", "3-5 years in
    # data engineering"), and only when nothing nearby says it is about something else.
    stated = bool(match.group("plus") or match.group("high") or lead in _REQUIRING_LEADS)
    near = before[-25:] + " " + window_after[:40]
    return stated and not _NOT_EXPERIENCE_NEAR.search(near) and not _COMPANY_VOICE.search(near)


def years_asked(description: str | None) -> YearsAsked | None:
    """The headline years of experience a posting asks for (highest stated minimum), or None."""
    text = description or ""
    best: YearsAsked | None = None
    for match in _MENTION.finditer(text):
        low = _number(match.group("low"))
        high = _number(match.group("high"))
        if low is None or low > _MAX_YEARS or not _credible(text, match):
            continue
        if high is not None and not low < high <= _MAX_YEARS:
            high = None
        if low == 0 and high is None:
            continue
        if best is None or low > best.minimum or (low == best.minimum and best.maximum is None and high):
            best = YearsAsked(low, high)
    return best

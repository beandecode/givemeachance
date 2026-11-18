"""Checks on a generated résumé or cover letter before the user sees it.

The prompts already forbid placeholders and invented facts, but a model can still slip. Hard problems
(leftover placeholders; a cover letter that never names the company, is far too short or too long, is not signed
with the candidate's name or uses stock phrases; a document that points at what the candidate lacks or hedges
("although I", "familiar with"); a résumé role at an employer that is not in the profile) earn one
retry with the problems listed; whatever remains, and softer observations (a number or a skill found nowhere in the
profile), are shown to the user as warnings. Nothing here blocks saving.

A résumé is a statement about the candidate, so its numbers must come from the profile alone; the posting's numbers
("5+ years") are only allowed in a cover letter, which answers the posting.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

_PLACEHOLDERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\[[^\]\n]{1,40}\](?!\()"), "a [bracketed] placeholder"),
    (re.compile(r"\{\{|\}\}"), "a {{template}} placeholder"),
    (re.compile(r"\bN/A\b", re.IGNORECASE), "the text N/A"),
    (re.compile(r"\bunknown\b", re.IGNORECASE), "the word 'unknown'"),
    (re.compile(r"\bTBD\b"), "the text TBD"),
    (re.compile(r"lorem ipsum", re.IGNORECASE), "lorem ipsum"),
)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_COMPANY_SUFFIXES = re.compile(
    r"[,.]?\s+(?:inc|incorporated|ltd|limited|llc|corp|corporation|co|gmbh|plc|ulc)\.?$", re.I
)
_UNKNOWN_COMPANY = {"", "unknown", "n/a", "none"}
COVER_LETTER_WORDS = (250, 350)  # what the prompt asks for; the model lands near 250 whatever it is asked
# Outside these bounds the letter is rewritten once: below, it is too thin to say anything; above, too long to be read.
MIN_COVER_LETTER_WORDS = 180
MAX_COVER_LETTER_WORDS = 450
_STOCK_PHRASES = re.compile(
    r"\bI am writing to\b|\bexpress(?:ing)? my (?:\w+ )?interest\b|\bperfect fit\b|\balign(?:s)? perfectly\b|"
    r"\bleverage my\b",
    re.I,
)
# Phrases that point at what the candidate lacks or play a strength down. The documents argue for the candidate.
_HEDGES = re.compile(
    r"\balthough I\b|\bwhile I (?:have not|haven't|lack|do not)\b|\bdespite (?:my|not|lacking)\b|"
    r"\bI (?:do not|don't) (?:yet )?have\b|\blimited (?:experience|exposure)\b|\bfamiliar with\b|"
    r"\bexposure to\b|\bbasic (?:knowledge|understanding)\b|\bsome experience\b",
    re.I,
)
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_BOLD_LINE = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")
_EXPERIENCE_SECTION = re.compile(r"experience|employment|work history", re.I)
_SKILLS_SECTION = re.compile(r"skills|technolog|tools|tech stack", re.I)
# Headings inside an experience section that are not a role.
_NOT_A_ROLE = re.compile(
    r"achievement|highlight|responsibilit|summary|project|skill|technolog|education|certification|award|"
    r"accomplishment|key |selected|additional",
    re.I,
)


@dataclass
class DocumentCheck:
    violations: list[str] = field(default_factory=list)  # worth one retry
    warnings: list[str] = field(default_factory=list)  # shown to the user, never block


def _numbers(text: str) -> set[str]:
    return {match.replace(",", "").rstrip(".") for match in _NUMBER.findall(text)}


def _company_core(company: str) -> str:
    name = str(company or "").strip()
    previous = None
    while previous != name:  # "Acme Co., Inc." -> "Acme"
        previous, name = name, _COMPANY_SUFFIXES.sub("", name).strip(" ,.")
    return name.casefold()


def _sections(content_md: str) -> list[tuple[str, list[str]]]:
    """(heading text, lines below it up to the next heading of the same or a higher level)."""
    found: list[tuple[str, int, list[str]]] = []
    for line in content_md.splitlines():
        heading = _HEADING.match(line)
        if heading:
            found.append((heading.group(2), len(heading.group(1)), []))
        elif found:
            found[-1][2].append(line)
    return [(title, lines) for title, _, lines in found]


def _unknown_roles(content_md: str, master_profile: dict | None) -> list[str]:
    """Roles listed under an experience heading whose employer and title are both absent from the profile."""
    experiences = (master_profile or {}).get("experiences")
    known: list[str] = []
    for entry in experiences if isinstance(experiences, list) else []:
        if isinstance(entry, dict):
            known += [str(entry.get(key) or "").strip().casefold() for key in ("company", "title")]
    known = [name for name in known if name and name not in _UNKNOWN_COMPANY and name != "experience"]
    if not known:
        return []

    problems: list[str] = []
    in_experience = False
    for line in content_md.splitlines():
        heading = _HEADING.match(line)
        if heading and len(heading.group(1)) <= 2:
            in_experience = bool(_EXPERIENCE_SECTION.search(heading.group(2)))
            continue
        if not in_experience:
            continue
        bold = _BOLD_LINE.match(line)
        role = heading.group(2) if heading else (bold.group(1) if bold else "")
        if not role or _NOT_A_ROLE.search(role):
            continue
        if not any(name in role.casefold() for name in known):
            problems.append(
                f"The résumé lists '{role.strip()}' as a role, but no such employer or title is in your profile"
            )
    return problems[:5]


def _unknown_skills(content_md: str, profile_text: str) -> list[str]:
    """One warning naming skills in the Skills section that appear nowhere in the profile."""
    haystack = profile_text.casefold()
    unknown: list[str] = []
    for title, lines in _sections(content_md):
        if not _SKILLS_SECTION.search(title):
            continue
        for line in lines:
            text = re.sub(r"^\s*[-*+]\s*", "", line)
            text = re.sub(r"^[^:]{1,30}:\s*", "", text)  # "Languages: Python, Go" -> "Python, Go"
            for item in re.split(r"[,;|•]", text):
                skill = item.strip(" *_`.")
                if 1 < len(skill) <= 40 and skill.casefold() not in haystack and skill not in unknown:
                    unknown.append(skill)
    if not unknown:
        return []
    return [f"These skills are not in your profile, remove them unless they are true: {', '.join(unknown[:8])}"]


def _candidate_name(master_profile: dict | None) -> str:
    identity = (master_profile or {}).get("identity")
    name = str(identity.get("name") or "").strip() if isinstance(identity, dict) else ""
    return "" if name.casefold() in _UNKNOWN_COMPANY or name.casefold() == "candidate" else name


def check_generated_document(
    kind: str,
    content_md: str,
    master_profile: dict | None,
    job: dict,
    match_report: dict | None = None,
) -> DocumentCheck:
    """`kind` is "resume" or "cover_letter"; `job` has title, company and description."""
    result = DocumentCheck()
    for pattern, label in _PLACEHOLDERS:
        if pattern.search(content_md):
            result.violations.append(f"The text contains {label}; remove it or write the real value")

    if kind == "cover_letter":
        company = str(job.get("company") or "")
        core = _company_core(company)
        if core and core not in _UNKNOWN_COMPANY and core not in content_md.casefold():
            result.violations.append(f"The letter never mentions the company by name ({company})")
        words = len(content_md.split())
        low, high = COVER_LETTER_WORDS
        if words > MAX_COVER_LETTER_WORDS:
            result.violations.append(f"The letter has {words} words; keep it to {high} words or fewer")
        elif words < MIN_COVER_LETTER_WORDS:
            result.violations.append(
                f"The letter has only {words} words; write {low} to {high} words with concrete achievements"
            )
        name = _candidate_name(master_profile)
        if name and name.casefold() not in content_md.casefold():
            result.violations.append(f"Sign the letter with the candidate's name exactly as written: {name}")
        stock = sorted({m.group(0).lower() for m in _STOCK_PHRASES.finditer(content_md)})
        if stock:
            result.violations.append(f"Replace the stock phrases: {', '.join(stock)}")

    profile_text = json.dumps(master_profile or {}, ensure_ascii=False)
    hedges = sorted(
        {m.group(0).lower() for m in _HEDGES.finditer(content_md)}
        - {m.group(0).lower() for m in _HEDGES.finditer(profile_text)}
    )
    if hedges:
        result.violations.append(
            f"Remove these phrases that point at gaps or play strengths down; show the closest real evidence instead: "
            f"{', '.join(hedges)}"
        )
    if kind == "resume":
        source_text = profile_text
        result.violations.extend(_unknown_roles(content_md, master_profile))
        result.warnings.extend(_unknown_skills(content_md, profile_text))
    else:
        source_text = (
            f"{profile_text} {job.get('title', '')} {job.get('description', '')} "
            f"{json.dumps(match_report or {}, default=str)}"
        )
    known = _numbers(source_text) | {"100", str(date.today().year), str(date.today().year - 1)}  # 100: "/100"
    unexplained = sorted(_numbers(content_md) - known, key=content_md.find)
    if unexplained:
        shown = ", ".join(unexplained[:5])
        where = "your profile" if kind == "resume" else "your profile or the posting"
        result.warnings.append(f"These numbers are not in {where}, please check them: {shown}")
    return result

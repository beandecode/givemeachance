from __future__ import annotations

import os
import re
import time

from core.schemas import EvaluationResult, JobRecord


def _simulate_latency() -> None:
    """Optional pause (MOCK_LLM_DELAY_SECONDS) so UI tests can observe running tasks; 0 by default."""
    delay = float(os.getenv("MOCK_LLM_DELAY_SECONDS", "0") or 0)
    if delay > 0:
        time.sleep(min(delay, 30))


def _sample_summary(user_details: dict, skills: list[str]) -> str:
    title = str(user_details.get("current_title", "")).strip() or "Software engineer"
    return f"{title} working with {', '.join(skills[:4])}." if skills else f"{title}."


def _sample_highlights(resume_text: str) -> list[str]:
    """The first full-sentence bullets of the pasted résumé, so sample profiles read like real ones."""
    bullets = [line.strip().lstrip("-•* ").strip() for line in resume_text.splitlines() if line.strip()[:1] in "-•*"]
    return [line for line in bullets if len(line.split()) >= 4][:3]


def _as_clause(text: str) -> str:
    """'Led the move ...' -> 'led the move ...', keeping acronyms such as 'AWS'."""
    text = str(text).strip().rstrip(".")
    return text[:1].lower() + text[1:] if text[1:2].islower() else text


_PAST_TENSE = {"built", "cut", "led", "ran", "wrote", "grew", "won", "made", "drove", "took", "set"}


def _reads_as_past(text: str) -> bool:
    """'Led ...' or 'Rebuilt ...' fit after 'I'; 'Owns ...' does not."""
    first = str(text).split(" ", 1)[0].casefold()
    return first.endswith("ed") or first in _PAST_TENSE or first.endswith("built")


def _sample_cover_letter(master_profile: dict, job: dict) -> str:
    """A full letter built only from the profile and the posting, so offline runs and the demo read like real use."""
    identity = master_profile.get("identity") if isinstance(master_profile.get("identity"), dict) else {}
    name = str(identity.get("name") or "").strip() or "Candidate"
    current = str(identity.get("current_title") or "").strip() or "software engineer"
    years = str(identity.get("years_experience") or "").strip()
    company = str(job.get("company") or "").strip() or "your company"
    title = str(job.get("title") or "").strip() or "this role"
    posting = f"{title} {job.get('description', '')}"
    skills = [str(skill) for skill in master_profile.get("core_skills", []) if str(skill).strip()]
    wanted = [skill for skill in skills if re.search(rf"(?<!\w){re.escape(skill)}(?!\w)", posting, re.I)] or skills
    wanted_text = _join(wanted[:3]) or "software engineering"

    results: list[tuple[str, str]] = []
    for role in master_profile.get("experiences", []) or []:
        if isinstance(role, dict):
            for item in [*role.get("achievements", []), *role.get("highlights", [])]:
                if _reads_as_past(item):
                    results.append((str(role.get("company") or "").strip(), str(item)))
    results.sort(key=lambda pair: not any(ch.isdigit() for ch in pair[1]))  # results with numbers first
    shown = results[:4]

    since = f"for the last {years} years " if years.isdigit() else ""
    opening = f"The {title} role at {company} centres on {wanted_text}, the work I have done {since}as a {current}."
    if shown:
        employer, text = shown[0]
        opening += f" The result most relevant to you: at {employer}, I {_as_clause(text)}."
    paragraphs = [opening]
    if len(shown) > 1:
        sentences, previous = [], shown[0][0]
        for employer, text in shown[1:]:
            if employer != previous:
                lead = f"At {employer}, I"
            else:
                lead = "I also" if not any(item.startswith("I also") for item in sentences) else "And I"
            sentences.append(f"{lead} {_as_clause(text)}.")
            previous = employer
        paragraphs.append("That was not a one-off. " + " ".join(sentences))
    projects = [p for p in master_profile.get("projects", []) or [] if isinstance(p, dict) and p.get("summary")]
    if projects:
        project = projects[0]
        summary = re.sub(r"^(A|An|The) ", lambda m: m.group(1).lower() + " ", str(project["summary"]).strip())
        paragraphs.append(
            f"Outside my day job I built {project.get('name', 'a side project')}, {summary.rstrip('.')}. Running it "
            "taught me to keep systems small enough that one person can understand, test and operate them."
        )
    preferences = master_profile.get("preferences") if isinstance(master_profile.get("preferences"), dict) else {}
    targets = [str(role) for role in preferences.get("target_roles", []) if str(role).strip()]
    why = f"What draws me to {company} is that this role puts {wanted_text} at the centre of the job."
    if targets:
        why += (
            f" I am looking for a {targets[0]} role where I own services from design to production, and the way "
            "this posting describes the team's work matches that."
        )
    paragraphs.append(why)
    paragraphs.append(
        "I would welcome a conversation about what your team needs next and how my experience could help. "
        "Thank you for your time and consideration."
    )
    body = "\n\n".join(paragraphs)
    return f"Dear Hiring Manager,\n\n{body}\n\nSincerely,\n{name}"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" and {items[-1]}" if items else ""


class MockGeminiEvaluator:
    """Deterministic evaluator used to verify pipeline feasibility without real API."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def evaluate(self, resume: dict, job: JobRecord) -> EvaluationResult:
        _simulate_latency()
        resume_skills = []
        for value in resume.get("skills", {}).values():
            resume_skills.extend(value)

        text = f"{job.title} {job.description}".lower()
        matched = [skill for skill in resume_skills if skill.lower() in text]
        gaps = ["Kubernetes", "CI/CD"] if len(matched) < 3 else ["System design depth"]

        # Keep score in a realistic range while preserving deterministic behavior.
        score = min(95, 50 + len(matched) * 8)
        recommendation = "strong_yes" if score >= 85 else "yes" if score >= 70 else "maybe" if score >= 55 else "no"
        confidence = "high" if len(matched) >= 4 else "medium" if len(matched) >= 2 else "low"

        return EvaluationResult(
            match_score=score,
            total_score=score,
            dimension_scores={
                "skills_match": min(100, 40 + len(matched) * 12),
                "experience_match": min(100, 45 + len(matched) * 10),
                "seniority_match": 70,
                "domain_match": min(100, 50 + len(matched) * 9),
                "location_salary_match": 65,
            },
            match_reasons=[
                f"Your profile covers {len(matched)} of the skills this posting asks for.",
                f"Strongest overlap: {', '.join(matched[:3])}."
                if matched
                else "Few of your listed skills appear here.",
            ],
            strengths=[f"{skill} is in the posting and in your profile" for skill in matched[:5]]
            or ["General engineering background"],
            gaps=gaps,
            risk_flags=["JD may omit deeper architecture expectations"] if score < 70 else [],
            recommendation_level=recommendation,
            confidence=confidence,
            missing_information=["Detailed team scope missing from pasted JD"] if "team" not in text else [],
            fit_reason=f"{len(matched)} of your skills appear in this posting.",
            should_apply=recommendation in {"strong_yes", "yes"},
            model_name=self.model_name,
        )

    def synthesize_master_profile(self, input_bundle: dict, attachments: list[dict]) -> dict:
        _simulate_latency()
        text = str(input_bundle.get("resume_text", "")).strip()
        extra = str(input_bundle.get("extra_context", "")).strip()
        user_details = input_bundle.get("user_details") if isinstance(input_bundle.get("user_details"), dict) else {}
        merged = f"{text}\n{extra}".lower()

        skill_names = {"python": "Python", "typescript": "TypeScript", "sql": "SQL", "flask": "Flask"}
        skill_names |= {"react": "React", "docker": "Docker", "aws": "AWS"}
        skills = [name for key, name in skill_names.items() if key in merged]

        links = input_bundle.get("links") if isinstance(input_bundle.get("links"), list) else []
        target_roles = user_details.get("target_roles") if isinstance(user_details.get("target_roles"), list) else []
        preferred_locations = (
            user_details.get("preferred_locations") if isinstance(user_details.get("preferred_locations"), list) else []
        )

        attachment_notes = [f"{item.get('name', 'file')} ({item.get('mime_type', 'unknown')})" for item in attachments]

        return {
            "identity": {
                "name": str(user_details.get("candidate_name", "unknown") or "unknown"),
                "current_title": str(user_details.get("current_title", "unknown") or "unknown"),
                "location": str(user_details.get("location", "unknown") or "unknown"),
                "years_experience": str(user_details.get("years_experience", "unknown") or "unknown"),
                "contact": {
                    "email": str(user_details.get("email", "unknown") or "unknown"),
                    "phone": str(user_details.get("phone", "unknown") or "unknown"),
                    "links": [str(item) for item in links if str(item).strip()],
                },
            },
            "profile_summary": _sample_summary(user_details, skills),
            "career_highlights": _sample_highlights(text),
            "core_skills": skills,
            "skill_matrix": {
                "languages": [skill for skill in skills if skill in {"Python", "TypeScript", "SQL"}],
                "frameworks": [skill for skill in skills if skill in {"Flask", "React"}],
                "cloud": [skill for skill in skills if skill == "AWS"],
                "data": [],
                "devops": [skill for skill in skills if skill == "Docker"],
                "tools": [],
                "domains": [],
            },
            "experiences": [
                {
                    "title": "Candidate Experience (mock)",
                    "company": "Unknown",
                    "location": str(user_details.get("location", "unknown") or "unknown"),
                    "employment_type": "unknown",
                    "start_date": "unknown",
                    "end_date": "unknown",
                    "duration": "unknown",
                    "highlights": [
                        "Generated from mock adapter",
                        f"Attachment count: {len(attachments)}",
                    ],
                    "achievements": [],
                    "tech_stack": skills,
                }
            ],
            "projects": [],
            "education": [],
            "certifications": [],
            "languages": [],
            "preferences": {
                "target_roles": [str(item) for item in target_roles if str(item).strip()],
                "preferred_locations": [str(item) for item in preferred_locations if str(item).strip()],
                "employment_types": [],
                "work_authorization": str(user_details.get("work_authorization", "unknown") or "unknown"),
            },
            "evidence_notes": attachment_notes or ["No attachment provided"],
            "missing_information": [
                {
                    "field": "experiences[].start_date/end_date",
                    "question": "Please provide timeline details for key experiences.",
                    "priority": "medium",
                }
            ],
            "field_confidence": [
                {
                    "field": "core_skills",
                    "confidence": 0.7,
                    "reason": "Mock extraction based on keyword matching.",
                }
            ],
            "completeness_score": 62,
            "model_name": self.model_name,
        }

    def rewrite_resume(
        self, master_profile: dict, job: dict, match_report: dict, style: str = "ats", fixes: list[str] | None = None
    ) -> dict:
        _simulate_latency()
        identity = master_profile.get("identity") if isinstance(master_profile.get("identity"), dict) else {}
        name = str(identity.get("name") or "").strip() or "Candidate"
        skills = ", ".join(master_profile.get("core_skills", [])[:8]) or "General engineering"
        lines = [f"# {name}", "", f"## Target role\n- {job.get('title', 'Unknown')} at {job.get('company', 'Unknown')}"]
        summary = str(master_profile.get("profile_summary") or "").strip()
        if summary:
            lines += ["", "## Summary", summary]
        lines += ["", "## Key skills", f"- {skills}"]
        highlights = [str(item) for item in master_profile.get("career_highlights", []) if str(item).strip()][:4]
        if highlights:
            lines += ["", "## Highlights", *[f"- {item}" for item in highlights]]
        roles = [item for item in master_profile.get("experiences", []) if isinstance(item, dict)][:3]
        if roles:
            lines += ["", "## Experience"]
            for role in roles:
                when = f"{role.get('start_date', '')} - {role.get('end_date', '')}".strip(" -")
                lines += ["", f"**{role.get('title', '')}**, {role.get('company', '')} ({when})"]
                lines += [f"- {item}" for item in list(role.get("highlights", []))[:2] if str(item).strip()]
        content = "\n".join(lines)
        return {
            "content_md": content,
            "evidence_notes": ["Generated by mock rewrite_resume", "Grounded in master_profile/core_skills"],
            "model_name": self.model_name,
        }

    def rewrite_cover_letter(
        self, master_profile: dict, job: dict, match_report: dict, tone: str = "formal", fixes: list[str] | None = None
    ) -> dict:
        _simulate_latency()
        return {
            "content_md": _sample_cover_letter(master_profile, job),
            "evidence_notes": ["Generated by mock rewrite_cover_letter", f"Tone={tone}"],
            "model_name": self.model_name,
        }

    def audit_document(self, master_profile: dict, content_md: str, kind: str) -> dict:
        """Every bullet is "supported" by the profile's skills; tests script this method to plant unsupported claims."""
        _simulate_latency()
        claims = [
            {
                "text": line.lstrip("-* ").strip(),
                "status": "supported",
                "profile_path": "core_skills",
                "quote": "",
            }
            for line in content_md.splitlines()
            if line.lstrip().startswith(("-", "*")) and line.lstrip("-* ").strip()
        ][:40]
        return {"claims": claims, "model_name": self.model_name}

from __future__ import annotations

from typing import Any

from core.document_checks import COVER_LETTER_WORDS
from core.job_text import is_description_snippet
from core.schemas import JobRecord


def build_evaluation_prompt(resume: dict, job: JobRecord) -> dict[str, Any]:
    return {
        "resume": resume,
        "job": {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description[:10000],  # the full posting (core/job_fulltext.py caps it at 10,000)
            "description_is_preview": is_description_snippet(job.source, job.description),
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
        },
        "task": (
            "Judge how well the candidate fits the job posting and answer with the JSON described in required_schema. "
            "You only rate each dimension; the total score and the recommendation are computed afterwards."
        ),
        "rules": [
            "Evidence first: every conclusion must rest on the posting or the candidate facts provided. Do not assume.",
            "Judge the way a hiring manager who wants to fill the role would: credit equivalent and transferable "
            "evidence. A different tool of the same kind, the same work done in another industry, and for an "
            "early-career candidate projects, internships, research, coursework and volunteer work all count as "
            "partial or full evidence for a requirement. Postings list more than they need; candidates who meet most "
            "of the core requirements are usually interviewed.",
            "If something is unknown or absent, say so under gaps or missing_information instead of guessing. "
            "Do not invent experience, responsibilities, company details or qualifications.",
            "Rate each dimension from 0 to 100 with this scale: 90-100 meets every stated requirement with direct, "
            "recent evidence; 70-89 meets most requirements, the gaps are minor or quickly learned; 50-69 partial "
            "overlap, several requirements unmet or unclear; 30-49 weak overlap, a core requirement is missing; "
            "below 30 unrelated. Use the whole scale; do not cluster around one value.",
            "seniority_match compares the level and scope the posting asks for (title, years required, ownership, "
            "leading others) with the candidate's years of experience and scope. A candidate far below or far above "
            "the level scores low. Set seniority_gap to role_is_more_senior, aligned, role_is_less_senior or unclear.",
            "missing_must_haves lists only hard gates the candidate's facts do not show and cannot be hired without: "
            "a licence, registration or certification the role legally requires (for example a nursing registration, "
            "CPA, P.Eng, a driver's licence for a driving job), a security clearance, a legal work requirement, or a "
            "degree the posting states as strictly mandatory. Years of experience and skills are never must-haves "
            "here: rate them in experience_match, seniority_match and skills_match. Leave it empty when none is "
            "missing.",
            "location_salary_match uses the candidate's preferred locations, work authorization and the salary range "
            "when the posting gives them; rate 60 when the posting says nothing.",
            "If job.description_is_preview is true the text is only the first 500 characters of the posting. Rate "
            "what it shows, do not mark the candidate down for requirements a preview would not mention, set "
            "confidence to low or medium and add 'full job description' to missing_information.",
            "strengths are things that make the candidate stand out for this posting, including spoken languages, "
            "licences and results the posting values; risk_flags are real obstacles such as a visa or authorization "
            "issue. match_reasons is a short chain of evidence.",
        ],
        "required_schema": {
            "dimension_scores": {
                "skills_match": "integer_0_to_100",
                "experience_match": "integer_0_to_100",
                "seniority_match": "integer_0_to_100",
                "domain_match": "integer_0_to_100",
                "location_salary_match": "integer_0_to_100",
            },
            "seniority_gap": "role_is_more_senior|aligned|role_is_less_senior|unclear",
            "missing_must_haves": ["string"],
            "match_reasons": ["string"],
            "strengths": ["string"],
            "gaps": ["string"],
            "risk_flags": ["string"],
            "confidence": "high|medium|low",
            "missing_information": ["string"],
            "fit_reason": "string",
        },
    }


def build_master_profile_synthesis_prompt(input_bundle: dict, attachments: list[dict]) -> dict[str, Any]:
    return {
        "task": (
            "Build a strict JSON master profile from the candidate's inputs, for any occupation (for example "
            "healthcare, trades, finance, education, retail, public service or technology). Every later step, from "
            "job matching to the résumé, uses only this profile, so capture every strength the inputs show. "
            "Do not invent facts, and output unknown for missing values."
        ),
        "rules": [
            "Never fabricate company names, timelines, or achievements.",
            "Keep every bullet and result the candidate wrote, in their own wording; do not merge, shorten or drop "
            "achievements. Standardize only spelling variants of the same name (for example 'React.js' and 'React').",
            "Capture licences and registrations in certifications; volunteer work as experiences with "
            "employment_type 'Volunteer'; awards, publications and notable results in career_highlights; spoken "
            "languages in languages.",
            "skill_matrix groups: languages = programming languages only; frameworks, cloud, data and devops are for "
            "technical profiles and stay empty otherwise; tools = software, systems, equipment and instruments; "
            "professional_skills = methods and practices of the occupation (for example patient assessment, "
            "financial reporting, lesson planning, inventory control, stakeholder management); domains = industries "
            "and specialties. tech_stack in experiences and projects lists the tools, software and methods used.",
            "Dates as YYYY-MM (or YYYY when only the year is given); end_date is 'present' for a current role. "
            "Never estimate a date that is not written (not from education years, neighbouring roles or a "
            "co-op term): leave it unknown, and the candidate is asked.",
            "years_experience is a number: years of professional work, not counting internships, co-ops, "
            "volunteering or study. current_title is the title of the most recent role.",
            "user_details are what the candidate typed in a form: they win over anything you infer.",
            "Each education entry is one string with everything given: degree, field, school, years, and honours, GPA "
            "or relevant coursework when stated. Each certification keeps its issuer and year when stated.",
            "If input_bundle.previous_profile is present, it is the candidate's current profile, possibly edited by "
            "hand: keep every fact in it and its order of experiences, and add input_bundle.supplement_answers "
            "where their field path points (experiences[1] is the second role in previous_profile).",
            "Extract both responsibilities and measurable outcomes. If numbers/metrics exist, prioritize capturing them.",
            "Consolidate redundant information across multiple uploaded documents into a single, cohesive timeline.",
            "Generate targeted `missing_information` questions for what would make the candidate stronger and is "
            "still unknown, most of all the result of a major role or project with no number. field is the exact "
            "path with list positions, for example experiences[1].achievements or projects[0].impact.",
            "Return compact but complete arrays (avoid empty strings).",
        ],
        "required_schema": {
            "identity": {
                "name": "string",
                "current_title": "string",
                "location": "string",
                "years_experience": "string",
                "contact": {
                    "email": "string",
                    "phone": "string",
                    "links": ["string"],
                },
            },
            "profile_summary": "string",
            "career_highlights": ["string"],
            "core_skills": ["string"],
            "skill_matrix": {
                "languages": ["string"],
                "frameworks": ["string"],
                "cloud": ["string"],
                "data": ["string"],
                "devops": ["string"],
                "tools": ["string"],
                "professional_skills": ["string"],
                "domains": ["string"],
            },
            "experiences": [
                {
                    "title": "string",
                    "company": "string",
                    "location": "string",
                    "employment_type": "string",
                    "start_date": "string",
                    "end_date": "string",
                    "duration": "string",
                    "highlights": ["string"],
                    "achievements": ["string"],
                    "tech_stack": ["string"],
                }
            ],
            "projects": [
                {
                    "name": "string",
                    "role": "string",
                    "duration": "string",
                    "summary": "string",
                    "impact": ["string"],
                    "tech_stack": ["string"],
                    "links": ["string"],
                }
            ],
            "education": ["string"],
            "certifications": ["string"],
            "languages": ["string"],
            "preferences": {
                "target_roles": ["string"],
                "preferred_locations": ["string"],
                "employment_types": ["string"],
                "work_authorization": "string",
            },
            "evidence_notes": ["string"],
            "missing_information": [
                {
                    "field": "string",
                    "question": "string",
                    "priority": "high|medium|low",
                }
            ],
            "field_confidence": [
                {
                    "field": "string",
                    "confidence": "number_between_0_and_1",
                    "reason": "string",
                }
            ],
            "completeness_score": "integer_0_to_100",
        },
        "input_bundle": input_bundle,
        "attachments_hint": [
            {"name": item.get("name", "file"), "mime_type": item.get("mime_type", "application/octet-stream")}
            for item in attachments
        ],
    }


def _retry_note(fixes: list[str] | None) -> list[str]:
    if not fixes:
        return []
    return [
        "Your previous draft was rejected for these problems. Write it again and fix every one: " + "; ".join(fixes)
    ]


_ADVOCATE = (
    "You work for the candidate. The goal is an interview: present the strongest true version of this candidate for "
    "this job. Every fact comes from master_profile; within that, choose, order and word everything to show why the "
    "candidate is a strong hire."
)
_ADVOCATE_RULES = [
    "Never invent employers, titles, dates, numbers, tools, degrees or results. Skills the profile shows in a role, a "
    "project or a tech stack are real and may be named in the posting's own wording.",
    "Never mention what the candidate lacks. match_report.requirements_not_met is there so you neither claim nor name "
    "those items; answer the need behind each with the closest real evidence instead, or leave it out.",
    "No hedging or self-deprecation: no 'basic', 'familiar with', 'exposure to', 'some experience', 'although', "
    "'despite', 'while I have not', 'rather than', unless the profile itself says so.",
    "Lead with results: what the candidate did and what changed, with the profile's numbers.",
]


def build_resume_rewrite_prompt(
    master_profile: dict, job: dict, match_report: dict, style: str = "ats", fixes: list[str] | None = None
) -> dict[str, Any]:
    return {
        "task": f"Write the résumé this candidate should send for this job, in Markdown. {_ADVOCATE}",
        "style": style,
        "constraints": [
            *_ADVOCATE_RULES,
            "Start with the candidate's name as a level-1 heading and one contact line from master_profile.identity.",
            "Then a Summary of two or three lines that positions the candidate for this role: their title or field, "
            "one or two of their strongest results that matter to this posting, with their numbers, and the skills the "
            "posting asks for that they have. No objective statement, no generic phrases such as 'proven record'.",
            "Order the sections by strength for this job. If the experience is short or far from the role, put "
            "Projects (and Education for a recent graduate) before Experience.",
            "Keep every role with its employer and dates so there are no unexplained gaps. Give the most relevant roles "
            "three to five bullets; shorten the others to one or two bullets that show transferable results.",
            "Within each role, put the bullets that matter most to this posting first. Start each bullet with a strong "
            "verb and end with the result, using the profile's numbers.",
            "Use the posting's exact words for skills and tools the candidate genuinely has, so keyword screening finds "
            "them. In Skills, list the ones the posting asks for first.",
            "Fit on one page for under ten years of experience: about 450 to 700 words.",
            "Leave out facts that are missing; never write placeholders such as 'unknown', 'N/A' or '[Company]'.",
            *_retry_note(fixes),
        ],
        "required_schema": {
            "content_md": "string",
            "evidence_notes": ["string"],
        },
        "master_profile": master_profile,
        "job": job,
        "match_report": match_report,
    }


def build_cover_letter_rewrite_prompt(
    master_profile: dict,
    job: dict,
    match_report: dict,
    tone: str = "formal",
    fixes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "task": (
            "Write the cover letter this candidate would send for this job: specific enough that the hiring manager "
            f"learns something the résumé alone does not say, and ready to send without editing. {_ADVOCATE}"
        ),
        "tone": tone,
        "constraints": [
            *_ADVOCATE_RULES,
            "About the employer, use only what the job posting says; never invent opinions about the company.",
            f"Length: {COVER_LETTER_WORDS[0]} to {COVER_LETTER_WORDS[1]} words, in four or five short paragraphs, plus the greeting and the sign-off.",
            "Greeting: 'Dear Hiring Manager,' unless the posting names the hiring manager or the team.",
            "Paragraph 1: name the role and the company, then give the single strongest reason to read on: the candidate achievement closest to what the posting needs most, with its number.",
            "Paragraphs 2 and 3: two or three concrete achievements from master_profile.experiences or projects, each with its employer or project and its numbers when the profile gives them, each tied to a requirement the posting states in its own words. For a recent graduate, projects, internships and coursework results carry this; never count years.",
            "Paragraph 4: why this company or this team, using specifics from the posting (what the organization does, who it serves, its products or services, its values or mission). If the posting gives nothing specific, say what about the role fits the candidate's goals in master_profile.preferences.",
            "State proactively only what removes a reason to reject and only as a plain positive fact: work authorization, location or relocation, availability. Nothing else that the candidate lacks.",
            "Closing: one or two sentences asking for a conversation, then 'Sincerely,' and the candidate's name exactly as master_profile.identity.name spells it.",
            "Say each point once. No skill lists, no repeated adjectives, no summary paragraph that restates the others.",
            "Avoid stock phrases: 'I am writing to', 'express my interest', 'I am confident that', 'perfect fit', 'align perfectly', 'passionate about', 'leverage my', 'fast-paced', 'dynamic team'.",
            "Leave out facts that are missing; never write placeholders such as 'unknown', 'N/A' or '[Company]'.",
            "Plain Markdown paragraphs; no headings, no bullet points, no address block.",
            *_retry_note(fixes),
        ],
        "required_schema": {
            "content_md": "string",
            "evidence_notes": ["string"],
        },
        "master_profile": master_profile,
        "job": job,
        "match_report": match_report,
    }


AUDIT_STATUSES = ("supported", "inferred", "unsupported")


def build_grounding_audit_prompt(master_profile: dict, content_md: str, kind: str) -> dict[str, Any]:
    """Ask a model to link every factual claim in a generated document to a fact in the Master Profile."""
    return {
        "task": "Act as a strict fact checker. List the factual claims a job-application document makes about the candidate and decide, for each, whether the master_profile supports it.",
        "constraints": [
            "A claim is a specific statement about the candidate: an employer, job title, date, number, skill, tool, degree, certification, achievement or responsibility. Skip greetings, opinions about the employer and trivial filler.",
            "supported: the master_profile states it, or the document words it differently without changing the facts.",
            "inferred: a reasonable reading of the master_profile that it does not state outright (for example a general soft skill).",
            "unsupported: the master_profile does not contain it or contradicts it. Be strict with employers, titles, dates, numbers, tools and degrees.",
            "profile_path is the dotted path of the supporting field (for example experiences[0].highlights[1]); quote is the exact words from the master_profile. Both are empty strings for unsupported claims.",
            "Judge facts only, never style. Do not invent claims that the document does not make. List at most 40 claims, the riskiest first.",
        ],
        "required_schema": {
            "claims": [
                {"text": "string", "status": "|".join(AUDIT_STATUSES), "profile_path": "string", "quote": "string"}
            ]
        },
        "document_kind": kind,
        "master_profile": master_profile,
        "document": content_md,
    }

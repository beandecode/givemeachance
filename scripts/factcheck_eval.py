# ruff: noqa: E501  (the cover letters keep one paragraph per line, as the app's writers produce them)
"""Fact-check test: how often the grounding audit catches false claims planted in documents (roadmap phase 11).

Hand-written documents about the fictional candidate in data/mock/demo_profile.json (Casey Chen), in two sets: "blunt"
(20 documents, wholly invented facts) and "subtle" (12 documents, real facts bent: wrong employer, bigger number or
scope, shifted dates, inflated title). Each is mostly true to the profile and plants one or two unsupported claims of a
known type. The app's
own audit (`audit_document`, ADR-016) reads each document against the profile; a planted claim counts as caught when an
audit claim marked "unsupported" contains one of its keywords. Every other audit claim should not be "unsupported":
the share that is, is the false-flag rate. Everything here is fictional, so the cases are committed.

    run      audit every document not yet audited for one model, into output_localtest/factcheck/<model>.json
             (inside a container that loads the provider keys; safe to run again after an
             interruption), then print the report:
                 docker exec -i <container> python - run --model <id> [--set blunt|subtle|all] [--limit N] \
                     < scripts/factcheck_eval.py
    report   print the Markdown table for saved results; calls no provider, so it runs on the host:
                 ./.venv/bin/python scripts/factcheck_eval.py report [output_localtest/factcheck/<model>.json ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_DIR = Path("output_localtest/factcheck")
PROFILE_FILE = Path("data/mock/demo_profile.json")
TYPES = ("employer", "title", "number", "certification", "skill", "education", "dates", "achievement")
SUBTLE_TYPES = ("misattribution", "inflation", "dates", "title", "credential", "project_swap", "combination")

# Each planted claim: its type and lowercase keywords that identify it in the audit's claim text. Every keyword is in
# the document and nowhere in the profile (tests/unit/test_factcheck_eval.py checks both), except in the subtle set
# where the false part is a real detail put in the wrong place: such a claim is marked "in_profile" and its keyword
# occurs once in the document, as a phrase of two or more words or a year.

# The blunt set: wholly invented employers, titles, numbers, certifications, tools, degrees, dates and achievements.
BLUNT_CASES: list[dict] = [
    {
        "id": "r01",
        "kind": "resume",
        "text": """# Casey Chen
Backend Engineer · Toronto, ON · casey.chen@example.com

## Summary
Backend engineer with five years of experience building Python services and data pipelines on AWS.

## Experience
**Backend Engineer, TrueNorth Analytics** (May 2022 – present)
- Led the move of the reporting API from Flask to FastAPI, cutting p95 latency from 820 ms to 190 ms
- Cut monthly AWS spend by 45% by rescheduling batch jobs and right-sizing ECS services
**Software Developer, Northwind Logistics** (2020 – 2022)
- Built REST integrations with payment and shipping providers (Flask, PostgreSQL, Redis)

## Education
BSc Computer Science, University of Waterloo (2019)
""",
        "planted": [
            {"type": "employer", "keywords": ["northwind"]},
            {"type": "number", "keywords": ["45%"]},
        ],
    },
    {
        "id": "r02",
        "kind": "resume",
        "text": """# Casey Chen
Toronto, ON · casey.chen@example.com · github.com/example

## Experience
**Engineering Manager, TrueNorth Analytics** (2022 – present)
- Owns the reporting API (FastAPI, PostgreSQL) used by more than 300 business customers
- Rebuilt nightly Airflow ETL jobs with retries and alerting; on-time delivery rose from 91% to 99.6%
**Software Developer, HarborStack** (2020 – 2022)
- Raised test coverage of the order service from 41% to 85%

## Skills
Python, SQL, FastAPI, PostgreSQL, AWS, Docker, Airflow

## Certifications
Certified Kubernetes Administrator (2023)
""",
        "planted": [
            {"type": "title", "keywords": ["engineering manager"]},
            {"type": "certification", "keywords": ["kubernetes"]},
        ],
    },
    {
        "id": "r03",
        "kind": "resume",
        "text": """# Casey Chen — Backend Engineer
casey.chen@example.com · +1-416-555-0137

## Experience
**Backend Engineer, TrueNorth Analytics, Toronto** (2022 – present)
- Built streaming ingestion with Kafka for the reporting API
- Introduced contract tests generated from the OpenAPI document, removing a class of breaking API changes
- Mentors two junior developers and runs the team's code-review guidelines
**Software Developer (co-op), MapleCloud, Waterloo** (summer 2018)
- Wrote Python tools that automated log collection for the support team

## Education
MSc Computer Science, University of Waterloo
""",
        "planted": [
            {"type": "skill", "keywords": ["kafka"]},
            {"type": "education", "keywords": ["msc"]},
        ],
    },
    {
        "id": "r04",
        "kind": "resume",
        "text": """# Casey Chen
Backend engineer, Toronto · Canadian permanent resident

## Experience
**Backend Engineer, TrueNorth Analytics** (May 2022 – present)
- Cut monthly AWS spend by 28% by rescheduling batch jobs and right-sizing services
- Won the company hackathon with a self-service report builder
**Software Developer, HarborStack** (2017 – 2022)
- Reduced failed provider callbacks by 70% with a queue-based retry design
- Built internal admin screens in React and TypeScript for the support team

## Projects
Open-source job queue for Postgres: a Python library on PostgreSQL row locks, 180 GitHub stars
""",
        "planted": [
            {"type": "dates", "keywords": ["2017"]},
            {"type": "achievement", "keywords": ["hackathon", "report builder"]},
        ],
    },
    {
        "id": "r05",
        "kind": "resume",
        "text": """# Casey Chen
Toronto, ON · casey.chen@example.com · linkedin.com/in/example

## Profile
Backend engineer with five years of Python, SQL and AWS experience; owns APIs from design to on-call.

## Experience
**Backend Engineer, TrueNorth Analytics** (2022 – present)
- Owns the reporting API used by 500+ business customers, including design reviews and on-call
- Moved the API from Flask to FastAPI with async database access; p95 latency fell from 820 ms to 190 ms
**Software Developer, HarborStack** (Jan 2020 – Apr 2022)
- Built REST integrations with payment and shipping providers for an e-commerce platform
- Added CI checks in GitHub Actions

## Certifications
AWS Certified Developer – Associate (2023)
""",
        "planted": [{"type": "number", "keywords": ["500"]}],
    },
    {
        "id": "r06",
        "kind": "resume",
        "text": """# Casey Chen
Backend Engineer · Toronto, ON

## Experience
**Backend Engineer, TrueNorth Analytics** (2022 – present)
- Rebuilt nightly ETL jobs in Airflow with retries, idempotent loads and alerting (on-time delivery 91% → 99.6%)
- Introduced contract tests from the OpenAPI document
**Software Developer, HarborStack** (2020 – 2022)
- Raised order-service test coverage from 41% to 85%
**Data Analyst, Bluepeak Software** (2019)

## Education
BSc Computer Science, University of Waterloo, graduated 2016
""",
        "planted": [
            {"type": "employer", "keywords": ["bluepeak", "data analyst"]},
            {"type": "dates", "keywords": ["2016"]},
        ],
    },
    {
        "id": "r07",
        "kind": "resume",
        "text": """# Casey Chen
casey.chen@example.com · Toronto, ON · open to remote in Canada

## Experience
**Tech Lead, TrueNorth Analytics** (May 2022 – present)
- Led the move from Flask to FastAPI, cutting p95 latency from 820 ms to 190 ms
- Cut monthly AWS spend by 28% by right-sizing ECS services and rescheduling batch jobs
- Mentors two junior developers
**Software Developer (co-op), MapleCloud** (May – Aug 2018)
- Added monitoring dashboards for a customer-facing file service

## Skills
Python, Go, FastAPI, SQLAlchemy, pytest, Terraform, Datadog, Redis
""",
        "planted": [{"type": "title", "keywords": ["tech lead"]}],
    },
    {
        "id": "r08",
        "kind": "resume",
        "text": """# Casey Chen
Backend and data engineer · Toronto, ON

## Experience
**Backend Engineer, TrueNorth Analytics** (2022 – present)
- Rebuilt nightly Airflow ETL jobs with retries and alerting, raising on-time delivery from 91% to 99.6%
- Loads reporting data into Snowflake for analytics customers
**Software Developer, HarborStack** (2020 – 2022)
- Reduced failed provider callbacks by 70% with a queue-based retry design

## Projects
Transit delay dashboard (2021): streams about 1 million rows a week into PostgreSQL

## Certifications
Google Cloud Professional Data Engineer (2024)
AWS Certified Developer – Associate (2023)
""",
        "planted": [
            {"type": "skill", "keywords": ["snowflake"]},
            {"type": "certification", "keywords": ["google cloud"]},
        ],
    },
    {
        "id": "r09",
        "kind": "resume",
        "text": """# Casey Chen
Backend Engineer · Toronto, ON · casey.chen@example.com

## Experience
**Backend Engineer, TrueNorth Analytics** (2022 – present)
- Owns a FastAPI and PostgreSQL reporting API serving 300+ business customers
- Introduced OpenAPI contract tests that removed a class of breaking API changes
**Software Developer, HarborStack** (2020 – 2022)
- Built internal admin screens in React and TypeScript
- Raised test coverage of the order service from 41% to 85%

## Education
BSc Computer Science, McGill University (2015 – 2019)

## Languages
English, Mandarin
""",
        "planted": [{"type": "education", "keywords": ["mcgill"]}],
    },
    {
        "id": "r10",
        "kind": "resume",
        "text": """# Casey Chen
Toronto, ON · github.com/example

## Experience
**Backend Engineer, TrueNorth Analytics** (2022 – present)
- Cut monthly AWS spend by 28% by rescheduling batch jobs
- Designed and launched the company's fraud-detection service
- Runs the team's code-review guidelines and mentors two junior developers
**Software Developer, HarborStack** (2020 – 2022)
- Built REST integrations with payment and shipping providers (Flask, PostgreSQL, Redis)

## Projects
Open-source job queue for Postgres (author): used in production by two teams

## Skills
Python, SQL, AWS (Lambda, ECS, S3, RDS), Docker, GitHub Actions
""",
        "planted": [{"type": "achievement", "keywords": ["fraud"]}],
    },
    {
        "id": "c01",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I am a backend engineer in Toronto with five years of experience building Python services and data pipelines on AWS, and I would like to join your platform team.

At TrueNorth Analytics I own a reporting API used by more than 300 business customers. I led its move from Flask to FastAPI, which brought p95 latency down from 820 ms to 190 ms, and I designed its GraphQL layer for partner integrations.

Before that I spent a year at Cobalt Health building patient-scheduling APIs, then joined HarborStack, where I built payment and shipping integrations and raised test coverage of the order service from 41% to 85%.

I enjoy working closely with data and product teams, and I would welcome a conversation.

Best regards,
Casey Chen
""",
        "planted": [
            {"type": "skill", "keywords": ["graphql"]},
            {"type": "employer", "keywords": ["cobalt", "patient-scheduling"]},
        ],
    },
    {
        "id": "c02",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I am writing to apply for the Backend Engineer role. I am currently a Senior Backend Engineer at TrueNorth Analytics in Toronto, where I own the reporting API from design reviews to on-call.

Reliability and cost matter to me. I rebuilt our nightly ETL jobs in Airflow with retries and alerting, so on-time delivery rose from 91% to 99.6%, and I cut monthly AWS spend by 28% by rescheduling batch jobs and right-sizing services.

I also mentor two junior developers and run the team's code-review guidelines, which has taught me to explain technical trade-offs clearly.

Thank you for your time.
Casey Chen
""",
        "planted": [{"type": "title", "keywords": ["senior"]}],
    },
    {
        "id": "c03",
        "kind": "cover_letter",
        "text": """Dear hiring team,

Your team's work on developer tooling caught my attention, and I think my background fits well.

In my own time I wrote an open-source Python library that runs background jobs on PostgreSQL row locks. It is used in production by two teams and has passed 1,200 stars on GitHub.

At work I am a backend engineer at TrueNorth Analytics, where I introduced contract tests generated from our OpenAPI document and removed a whole class of breaking API changes. Earlier, at HarborStack, I designed a queue-based retry system that reduced failed provider callbacks by 70%.

I care about tools that make other engineers faster, and I would be glad to talk.

Sincerely,
Casey Chen
""",
        "planted": [{"type": "number", "keywords": ["1,200"]}],
    },
    {
        "id": "c04",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I would like to apply for the Platform Engineer position. I have been a backend engineer at TrueNorth Analytics since 2024, and before that I was a software developer at HarborStack in Toronto.

I hold the AWS Certified Solutions Architect – Professional certification and use AWS every day: Lambda, ECS, S3 and RDS, managed with Terraform. Rescheduling batch jobs and right-sizing our ECS services cut monthly AWS spend by 28%.

I am a Canadian permanent resident based in Toronto and open to remote work in Canada.

Kind regards,
Casey Chen
""",
        "planted": [
            {"type": "certification", "keywords": ["solutions architect"]},
            {"type": "dates", "keywords": ["2024"]},
        ],
    },
    {
        "id": "c05",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I am a Toronto-based backend engineer with five years of experience, mostly in Python, PostgreSQL and AWS.

At TrueNorth Analytics I rebuilt our nightly Airflow ETL jobs with idempotent loads and alerting, lifting on-time delivery from 91% to 99.6%. Last year I presented that work as a speaker at PyCon Canada.

I also built a transit delay dashboard as a side project; it streams about a million rows a week into PostgreSQL.

I like owning a service end to end, from design to on-call. I would welcome the chance to discuss the role.

Best,
Casey Chen
""",
        "planted": [{"type": "achievement", "keywords": ["pycon"]}],
    },
    {
        "id": "c06",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I am applying for the Data Engineer role. Since 2022 I have built data pipelines and APIs at TrueNorth Analytics, and before that I built payment integrations at Lakeshore Bank.

At TrueNorth I rebuilt nightly ETL jobs in Airflow with retries and idempotent loads, and on-time delivery rose from 91% to 99.6%. I work in Python, SQL, pandas and PostgreSQL.

I communicate well across teams: I work closely with our data and product colleagues and mentor two junior developers.

Thank you for considering my application.
Casey Chen
""",
        "planted": [{"type": "employer", "keywords": ["lakeshore"]}],
    },
    {
        "id": "c07",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I am a backend engineer with five years of experience and a BSc in Computer Science from the University of Waterloo. I later completed an MBA part-time, which helps me connect engineering work to business results.

At TrueNorth Analytics I process large reporting datasets with Apache Spark and Airflow, and I cut monthly AWS spend by 28% by rescheduling batch jobs. At HarborStack I built REST integrations with payment and shipping providers using Flask, PostgreSQL and Redis.

I am excited about the chance to bring that experience to your team.

Regards,
Casey Chen
""",
        "planted": [
            {"type": "education", "keywords": ["mba"]},
            {"type": "skill", "keywords": ["spark"]},
        ],
    },
    {
        "id": "c08",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I studied Computer Science at the University of Waterloo from 2013 to 2017 and did a software co-op at MapleCloud, where I wrote Python tools that automated log collection for the support team.

Since then I have worked as a software developer at HarborStack and now as a backend engineer at TrueNorth Analytics, where I own the reporting API and take part in on-call. I am also a Certified ScrumMaster and help the team plan its sprints.

I enjoy mentoring: I currently mentor two junior developers.

Best regards,
Casey Chen
""",
        "planted": [
            {"type": "dates", "keywords": ["2013", "2017"]},
            {"type": "certification", "keywords": ["scrum", "sprints"]},
        ],
    },
    {
        "id": "c09",
        "kind": "cover_letter",
        "text": """Dear hiring team,

As a Principal Engineer at TrueNorth Analytics I own the reporting API that more than 300 business customers rely on, from design reviews to on-call.

I care about the people around me as much as the systems: I mentor five junior developers and run the team's code-review guidelines. I also introduced contract tests from our OpenAPI document, which removed a class of breaking API changes.

Earlier, at HarborStack, I raised the order service's test coverage from 41% to 85% and added CI checks in GitHub Actions.

I would be glad to talk about how I could help your team.
Casey Chen
""",
        "planted": [
            {"type": "title", "keywords": ["principal"]},
            {"type": "number", "keywords": ["five junior"]},
        ],
    },
    {
        "id": "c10",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I am a Toronto backend engineer who enjoys turning messy data into reliable products.

At TrueNorth Analytics I led the move of our reporting API from Flask to FastAPI, with async database access, and p95 latency fell from 820 ms to 190 ms. I also built the company's customer-facing mobile app.

At HarborStack I built internal admin screens in React and TypeScript for the support team, and a queue-based retry design that reduced failed provider callbacks by 70%.

I am a Canadian permanent resident and available for full-time work in Toronto or remotely.

Sincerely,
Casey Chen
""",
        "planted": [{"type": "achievement", "keywords": ["mobile app"]}],
    },
]

# The subtle set: real facts bent a little. A skill credited to the wrong employer, a result with a bigger number or
# scope, shifted dates, an inflated title, a real credential with the wrong school or year, one project's result on
# another, and profile tools combined into work the profile never describes.
SUBTLE_CASES: list[dict] = [
    {
        "id": "sr01",
        "kind": "resume",
        "text": """# Casey Chen
Backend Engineer · Toronto, ON

## Experience
**Backend Engineer, TrueNorth Analytics** (May 2022 – present)
- Rebuilt nightly Airflow ETL jobs with retries and idempotent loads; on-time delivery rose from 91% to 99.9%
- Moved the reporting API from Flask to FastAPI with async database access (p95 820 ms → 190 ms)
**Software Developer, HarborStack** (Jan 2020 – Apr 2022)
- Built REST integrations with payment and shipping providers (Flask, PostgreSQL, Redis)
- Managed the company's AWS infrastructure with Terraform
- Raised test coverage of the order service from 41% to 85%

## Education
BSc Computer Science, University of Waterloo (2015 – 2019)
""",
        "planted": [
            {"type": "inflation", "keywords": ["99.9%"]},
            {"type": "misattribution", "keywords": ["infrastructure"]},
        ],
    },
    {
        "id": "sr02",
        "kind": "resume",
        "text": """# Casey Chen
Toronto, ON · casey.chen@example.com

## Experience
**Lead Backend Engineer, TrueNorth Analytics** (2022 – present)
- Owns the reporting API (FastAPI, PostgreSQL) used by 300+ business customers, including on-call
- Introduced contract tests from the OpenAPI document, removing a class of breaking API changes
**Software Developer, HarborStack** (2020 – 2023)
- Reduced failed provider callbacks by 70% with a queue-based retry design
- Built internal admin screens in React and TypeScript for the support team

## Skills
Python, SQL, FastAPI, Flask, PostgreSQL, Redis, React, TypeScript
""",
        "planted": [
            {"type": "title", "keywords": ["lead backend"]},
            {"type": "dates", "keywords": ["2023"], "in_profile": True},
        ],
    },
    {
        "id": "sr03",
        "kind": "resume",
        "text": """# Casey Chen
Backend Engineer · Toronto, ON · github.com/example

## Experience
**Backend Engineer, TrueNorth Analytics** (2022 – present)
- Cut monthly AWS spend by 28% by rescheduling batch jobs and right-sizing ECS services
- Mentors two junior developers and runs the team's code-review guidelines
**Software Developer, HarborStack** (2020 – 2022)
- Raised order-service test coverage from 41% to 85% and added CI checks in GitHub Actions

## Projects
Open-source Postgres job queue (author): runs background jobs on row locks and processes about 1 million jobs a week

## Certifications
AWS Certified Developer – Associate (2021)
""",
        "planted": [
            {"type": "project_swap", "keywords": ["million jobs"]},
            {"type": "credential", "keywords": ["2021"], "in_profile": True},
        ],
    },
    {
        "id": "sr04",
        "kind": "resume",
        "text": """# Casey Chen
Toronto, ON · casey.chen@example.com · Canadian permanent resident

## Experience
**Backend Engineer, TrueNorth Analytics** (May 2022 – present)
- Rebuilt all of the company's data pipelines in Airflow, with retries and alerting
- Built a Go service on AWS Lambda that serves the reporting API's exports
- Led the move from Flask to FastAPI, cutting p95 latency from 820 ms to 190 ms
**Software Developer, HarborStack** (Jan 2020 – Apr 2022)
- Built REST integrations with payment and shipping providers for an e-commerce platform

## Skills
Python, Go, SQL, FastAPI, Airflow, AWS (Lambda, ECS, S3, RDS), Terraform
""",
        "planted": [
            {"type": "inflation", "keywords": ["all of the company"]},
            {"type": "combination", "keywords": ["go service"]},
        ],
    },
    {
        "id": "sr05",
        "kind": "resume",
        "text": """# Casey Chen
Backend Engineer · Toronto, ON

## Experience
**Backend Engineer, TrueNorth Analytics** (2022 – present)
- Built internal admin screens in React and TypeScript for the customer success team
- Rebuilt nightly ETL jobs with idempotent loads and alerting (on-time delivery 91% → 99.6%)
**Software Developer, HarborStack** (2020 – 2022)
- Reduced failed provider callbacks by 70% with a queue-based retry design
**Software Developer (co-op), MapleCloud** (May 2018 – Apr 2019)
- Wrote Python tools that automated log collection for the support team
""",
        "planted": [
            {"type": "misattribution", "keywords": ["admin screens"], "in_profile": True},
            {"type": "dates", "keywords": ["2019"], "in_profile": True},
        ],
    },
    {
        "id": "sr06",
        "kind": "resume",
        "text": """# Casey Chen
casey.chen@example.com · Toronto, ON

## Experience
**Backend Engineer, TrueNorth Analytics** (2022 – present)
- Leads a team of two junior developers and runs the team's code-review guidelines
- Introduced contract tests from the OpenAPI document
- Cut monthly AWS spend by 28% by rescheduling batch jobs
**Senior Software Developer, HarborStack** (2020 – 2022)
- Built REST integrations with payment and shipping providers (Flask, PostgreSQL, Redis)
- Added CI checks in GitHub Actions

## Certifications
AWS Certified Developer – Associate (2023)
""",
        "planted": [
            {"type": "inflation", "keywords": ["leads a team"]},
            {"type": "title", "keywords": ["senior software"]},
        ],
    },
    {
        "id": "sc01",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I am a backend engineer in Toronto with five years of experience in Python, PostgreSQL and AWS.

At TrueNorth Analytics I own the reporting API from design reviews to on-call, and I cut monthly AWS spend by 28% across the whole company by rescheduling batch jobs and right-sizing ECS services.

Before that, at HarborStack, I built the payment and shipping integrations in FastAPI and raised test coverage of the order service from 41% to 85%.

I like working closely with data and product teams, and I would welcome a conversation.

Best regards,
Casey Chen
""",
        "planted": [
            {"type": "inflation", "keywords": ["whole company"]},
            {"type": "misattribution", "keywords": ["in fastapi"]},
        ],
    },
    {
        "id": "sc02",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I would like to apply for the Platform Engineer role. I have been a backend engineer at TrueNorth Analytics since 2021, where I own the reporting API and take part in on-call.

I wrote the Terraform modules for our Airflow cluster, and I rebuilt the nightly ETL jobs with retries and alerting so on-time delivery rose from 91% to 99.6%.

I also mentor two junior developers, which has made me better at explaining technical decisions.

Kind regards,
Casey Chen
""",
        "planted": [
            {"type": "dates", "keywords": ["2021"], "in_profile": True},
            {"type": "combination", "keywords": ["terraform modules"]},
        ],
    },
    {
        "id": "sc03",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I am a backend engineer with a BSc in Computer Science from the University of Toronto and five years of experience building Python services.

My transit delay dashboard, which collects public transit data every minute, has 180 GitHub stars, and my open-source job queue for Postgres runs in production at two teams.

At TrueNorth Analytics I introduced contract tests from our OpenAPI document, which removed a class of breaking API changes.

I would be glad to talk about the role.

Sincerely,
Casey Chen
""",
        "planted": [
            {"type": "credential", "keywords": ["university of toronto"]},
            {"type": "project_swap", "keywords": ["180 github stars"]},
        ],
    },
    {
        "id": "sc04",
        "kind": "cover_letter",
        "text": """Dear hiring team,

As the lead engineer on TrueNorth Analytics' reporting API, I own a FastAPI and PostgreSQL service that more than 300 business customers use, from design reviews to on-call.

I moved it from Flask to FastAPI with async database access, which brought p95 latency down from 820 ms to 190 ms. At HarborStack before that, a queue-based retry design I built reduced failed provider callbacks by 70%.

Reliability and cost matter to me, and I enjoy working closely with product teams.

Best,
Casey Chen
""",
        "planted": [{"type": "title", "keywords": ["lead engineer"]}],
    },
    {
        "id": "sc05",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I have been building backend systems since my co-op at MapleCloud in Waterloo, where I wrote Python tools that automated log collection and added monitoring dashboards in Datadog for a customer-facing file service.

Today I am a backend engineer at TrueNorth Analytics. I rebuilt our nightly Airflow ETL jobs with idempotent loads and alerting, and on-time delivery rose from 91% to 99.6%.

I am a Canadian permanent resident in Toronto and I speak English and Mandarin.

Regards,
Casey Chen
""",
        "planted": [{"type": "misattribution", "keywords": ["dashboards in datadog"]}],
    },
    {
        "id": "sc06",
        "kind": "cover_letter",
        "text": """Dear hiring team,

I am applying for the Backend Engineer role. At HarborStack I led a team of four that built REST integrations with payment and shipping providers for our e-commerce platform, using Flask, PostgreSQL and Redis.

Since May 2022 I have been a backend engineer at TrueNorth Analytics, where I cut monthly AWS spend by 28% and introduced contract tests from our OpenAPI document.

I explain technical trade-offs clearly and enjoy mentoring; I currently mentor two junior developers.

Thank you for your time.
Casey Chen
""",
        "planted": [{"type": "inflation", "keywords": ["team of four"]}],
    },
]
SETS = {"blunt": BLUNT_CASES, "subtle": SUBTLE_CASES}
CASES = BLUNT_CASES + SUBTLE_CASES

_LOOSE = re.compile(r"[\s,]+")


def normalize(text: str) -> str:
    """Lowercase without spaces or commas, so "120 ms" matches "120ms" and "1,200" matches "1200"."""
    return _LOOSE.sub("", text.lower())


def matches(planted: dict, claim_text: str) -> bool:
    text = normalize(claim_text)
    return any(normalize(keyword) in text for keyword in planted["keywords"])


def score_case(case: dict, claims: list[dict]) -> dict:
    """Which planted claims the audit caught, and how it judged every claim that matches none of them."""
    caught = [
        any(c.get("status") == "unsupported" and matches(p, c.get("text", "")) for c in claims) for p in case["planted"]
    ]
    others = [c for c in claims if not any(matches(p, c.get("text", "")) for p in case["planted"])]
    return {"caught": caught, "others": others}


def evaluate(cases: list[dict], results: dict) -> dict:
    """The report numbers for one model; `results` maps a case id to {"claims": [...], "seconds": ...} or {"error"}."""
    by_type: dict[str, list[int]] = {}  # type -> [caught, planted], in the order the cases name them
    planted = caught = all_caught = audited = other = flagged = 0
    examples: list[dict] = []
    seconds: list[float] = []
    for case in cases:
        result = results.get(case["id"])
        if not result or "claims" not in result:
            continue
        audited += 1
        if "seconds" in result:
            seconds.append(float(result["seconds"]))
        scored = score_case(case, result["claims"])
        for item, hit in zip(case["planted"], scored["caught"], strict=True):
            counts = by_type.setdefault(item["type"], [0, 0])
            counts[0] += hit
            counts[1] += 1
        planted += len(case["planted"])
        caught += sum(scored["caught"])
        all_caught += all(scored["caught"])
        other += len(scored["others"])
        for claim in scored["others"]:
            if claim.get("status") == "unsupported":
                flagged += 1
                examples.append({"id": case["id"], "text": claim.get("text", "")})
    seconds.sort()
    return {
        "documents": audited,
        "planted": planted,
        "caught": caught,
        "by_type": {kind: (value[0], value[1]) for kind, value in by_type.items()},
        "all_caught": all_caught,
        "other_claims": other,
        "false_flags": flagged,
        "false_flag_examples": examples,
        "median_seconds": seconds[len(seconds) // 2] if seconds else None,
    }


def _share(part: int, whole: int) -> str:
    return f"{part} of {whole} ({part / whole:.0%})" if whole else "-"


def format_report(name: str, result: dict, usage: dict | None = None, examples: int = 8) -> str:
    lines = [
        f"{name}: {result['documents']} documents audited",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Planted claims caught | {_share(result['caught'], result['planted'])} |",
    ]
    for kind, (hit, total) in result["by_type"].items():
        lines.append(f"| - {kind} | {_share(hit, total)} |")
    lines += [
        f"| Documents with every planted claim caught | {_share(result['all_caught'], result['documents'])} |",
        f"| Other claims marked unsupported (false flags) | {_share(result['false_flags'], result['other_claims'])} |",
    ]
    if result["median_seconds"] is not None:
        lines.append(f"| Median seconds per audit | {result['median_seconds']} |")
    if usage and usage.get("input_tokens"):
        lines.append(f"| Tokens | {usage['input_tokens']} in, {usage.get('output_tokens', 0)} out |")
    if result["false_flag_examples"]:
        lines += ["", "False flags (judge by hand: test-author error or model mistake):"]
        lines += [f"- {item['id']}: {item['text']}" for item in result["false_flag_examples"][:examples]]
    return "\n".join(lines)


def set_of(case_id: str) -> str:
    return next(name for name, cases in SETS.items() if any(case["id"] == case_id for case in cases))


def report_sets(model: str, data: dict) -> str:
    """One table per set that has results; tokens are kept per set (`usage_by_set`)."""
    tables = []
    for name, cases in SETS.items():
        result = evaluate(cases, data.get("results", {}))
        if result["documents"]:
            tables.append(format_report(f"{model}, {name} set", result, data.get("usage_by_set", {}).get(name)))
    return "\n\n".join(tables)


def run(folder: Path, model: str, limit: int | None, pause: float, case_set: str = "all") -> None:
    """Audit every document not yet audited for `model`; safe to run again after an interruption."""
    import time

    from adapters.llm.gemini_api import GeminiApiEvaluator

    usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    llm = GeminiApiEvaluator(model_name=model, db_path=None)  # no app quota: this tool counts its own calls
    post = llm._post

    def counted(body: dict) -> object:
        usage["calls"] += 1
        payload = post(body)
        meta = payload.get("usageMetadata", {}) if isinstance(payload, dict) else {}
        usage["input_tokens"] += int(meta.get("promptTokenCount", 0))
        usage["output_tokens"] += int(meta.get("candidatesTokenCount", 0)) + int(meta.get("thoughtsTokenCount", 0))
        return payload

    llm._post = counted  # type: ignore[method-assign]
    profile = json.loads(PROFILE_FILE.read_text())
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{model}.json"
    saved: dict = json.loads(out.read_text()) if out.exists() else {"model": model}
    results: dict[str, dict] = saved.setdefault("results", {})
    by_set: dict[str, dict[str, int]] = saved.setdefault("usage_by_set", {})
    cases = CASES if case_set == "all" else SETS[case_set]
    todo = [case for case in cases if "claims" not in results.get(case["id"], {})][:limit]
    for case in todo:
        started = time.monotonic()
        try:
            audited = llm.audit_document(profile, case["text"], case["kind"])
            results[case["id"]] = {"claims": audited["claims"], "seconds": round(time.monotonic() - started, 1)}
        except Exception as error:  # noqa: BLE001 (record and go on: one bad reply must not lose the run)
            results[case["id"]] = {"error": f"{type(error).__name__}: {error}"[:200]}
        spent = by_set.setdefault(set_of(case["id"]), {})
        for key, value in usage.items():
            spent[key] = spent.get(key, 0) + value
            usage[key] = 0
        out.write_text(json.dumps(saved, indent=1, ensure_ascii=False))
        time.sleep(pause)
    for case_id, item in results.items():
        if "error" in item:
            print(f"  failed {case_id}: {item['error']}", file=sys.stderr)
    print(report_sets(model, saved))


def report(folder: Path, files: list[Path]) -> None:
    paths = files or sorted(folder.glob("*.json"))
    if not paths:
        sys.exit(f"No results in {folder}; run `run` first")
    for path in paths:
        data = json.loads(path.read_text())
        print(report_sets(data.get("model", path.stem), data))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("run")
    audit.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    audit.add_argument("--model", required=True)
    audit.add_argument("--set", dest="case_set", choices=("blunt", "subtle", "all"), default="all")
    audit.add_argument("--limit", type=int, default=None, help="audit at most this many documents in this run")
    audit.add_argument("--pause", type=float, default=2.0, help="seconds between calls (provider rate limits)")
    show = commands.add_parser("report")
    show.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    show.add_argument("results", nargs="*", type=Path, help="results files (default: every file in --dir)")
    args = parser.parse_args()
    if args.command == "run":
        run(args.dir, args.model, args.limit, args.pause, args.case_set)
    else:
        report(args.dir, args.results)


if __name__ == "__main__":
    main()

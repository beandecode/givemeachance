# Roadmap

Planned work and its status, one phase at a time. Start with the status table; each phase below has the detail.

**Direction:** a job-search assistant shown as a portfolio piece — a safe public demo and a closed-registration app; no
open sign-up. Flask + SQLite stay ([ADR-005](adr/ADR-005-product-fit-and-growth-triggers.md)); PostgreSQL or an
external queue only if measured needs appear.

## Status

| Phase | State | What is left |
|---|---|---|
| 0–10, 12 | Done | — ([short record](#done)) |
| [11 Prove the matching](#phase-11--prove-the-matching-and-the-fact-check) | Done | — |
| [13 Job supply](#phase-13--job-supply) | Planned | Entry-level search for new graduates, URL import |
| [14 Data and account safety](#phase-14--data-and-account-safety) | Planned | Backups, export and delete, account self-service |
| [15 Task reliability and types](#phase-15--task-reliability-and-types) | Planned | Retries, chained tasks, structured output, mypy |

## Done

Details are in the ADRs and the code; this is the short record.

- **0 Docs, safety, tooling** — one entry point (`CONTRIBUTING.md`), secrets out of compose files, ruff, mypy, hash-locked
  dependencies, CI with secret scan
- **1 Backend reliability** — numbered migrations on SQLite in WAL mode, no transaction across a provider call, quota
  that survives rollbacks, typed Gemini errors with no fabricated output, task heartbeat and recovery, health checks,
  sign-in throttling, non-root Docker image
- **2 API** — typed `/api/v1` with one error envelope and a committed OpenAPI document, PDF and DOCX export
  ([ADR-006](adr/ADR-006-typed-api-layer.md), [ADR-007](adr/ADR-007-pure-python-export.md))
- **3 Web app** — React + TypeScript at `/app`, generated API types, browser tests with accessibility checks
  ([ADR-008](adr/ADR-008-react-spa.md))
- **4 Demo** — read-only demo mode with seeded sample data ([ADR-009](adr/ADR-009-read-only-demo-mode.md))
- **5 Legacy removed** — the Jinja UI and the unversioned routes are gone; settings are immutable
- **6 Useful real results** — job levels, scoring computed in code, snippet awareness, structured logging, document
  checks ([ADR-010](adr/ADR-010-scoring-computed-in-code.md))
- **7 and 8 Design** — Neon Glass look for phone and desktop, swipe deck, search under the user's control
  ([ADR-011](adr/ADR-011-design-language-and-fonts.md) to [ADR-014](adr/ADR-014-user-controlled-search-and-scoring.md))
- **9 Guidance, trust, funnel** — guided flow, documents checked against the profile, hard filters and a relevance
  pre-score before any AI call ([ADR-015](adr/ADR-015-guided-journey.md) to [ADR-017](adr/ADR-017-search-funnel.md))
- **10 Visible** — public demo with live guest workspaces ([ADR-018](adr/ADR-018-live-demo-guest-workspaces.md)), a
  first-visit tour, a complete sample profile, résumé input from a sample in every format and sample gap questions;
  documents that argue for the candidate and never name a gap ([ADR-016](adr/ADR-016-grounded-documents.md));
  screenshots and tour GIFs
- **12 Published** — audit for secrets and personal data, MIT licence, case study page at `/case-study`

## Phase 11 — Prove the matching and the fact check

The measure is the score against fit, above all the level labels; apply decisions are for reference only. The deck threshold stays a user setting. Results so far are in the README ("How well it scores") and in
[ADR-010](adr/ADR-010-scoring-computed-in-code.md) and [ADR-019](adr/ADR-019-full-job-descriptions.md).

- [x] Labelled set: 48 real postings collected, 47 labelled blind to the scores; data in the gitignored
  `output_localtest/labelling/` ([how](operations.md#measuring-match-quality))
- [x] Full job descriptions read from the job board's page; scoring on `gemini-3.5-flash-lite`
- [x] Must-have rule limited to hard gates, transferable evidence credited
- [x] Profile building keeps every fact; matching and documents work for any occupation
- [x] `scripts/labelling.py report`: one command prints the README table from the labels and the scores, with
  confidence intervals (48 postings is a small set)
- [x] Fact-check test: 32 documents (20 blunt, 12 subtle) with planted unsupported claims; share caught and share of true claims flagged;
  try `gemini-3.8-flash` as `llm.document_model` / `llm.audit_model`
- [x] Model comparison table: the four models' agreement with the labels, cost per 100 jobs and seconds per job
- [x] Level as its own signal: the years of experience a posting asks for, read from the full text, shown on the card,
  the row and the job page ("asks for 5+ years"), next to the score
- Acceptance: one command re-runs the evaluation on the localtest stack and reproduces the README numbers

## Phase 13 — Job supply

- [ ] Entry-level search for new graduates: a level choice that searches "new grad", "junior", "entry level" and
  "associate" postings (only 7 junior data-science postings in Toronto in a month, against 20+ for every other query)
- [ ] URL import: paste a job link; read its schema.org `JobPosting` data with the same reader as the job board
  (`core/job_fulltext.py`), opened to other hosts with private-address, size and time limits
- [ ] A second job source, also the fallback if the job board stops serving its detail pages
- [ ] Several keywords and locations per search within the shown quota
- [ ] Daily scheduled search for the owner account
- [ ] Relevance shown as "likely fit" on unscored rows
- Acceptance: a week of real use gives a non-empty deck every day without pasting descriptions by hand

## Phase 14 — Data and account safety

- [ ] Nightly SQLite backup and a rehearsed restore, described in `docs/operations.md`
- [ ] Personal data export and delete
- [ ] Change password, server-side session revocation, longer minimum password
- [ ] Sign-in throttling by growing delay instead of a lockout a stranger can trigger
- [ ] `pip-audit` and `npm audit` in CI; HSTS and a content security policy on API responses
- Acceptance: one restore rehearsed from a backup; auth tests cover every item

## Phase 15 — Task reliability and types

- [ ] Automatic retry with backoff for transient provider errors; interrupted tasks that are safe to repeat are queued again
- [ ] "Re-score and write" as one queued chain
- [ ] Gemini `responseSchema` (structured output); invalid-response rate before and after
- [ ] Gemini adapter, evaluation and task handlers leave the mypy override list
- [ ] Later, unscheduled: gunicorn 26 / Python 3.14, pass settings through `app.config`, application timeline,
  cursor pagination
- Acceptance: killing a worker in the middle of a task ends in a finished task

## Backlog (unscheduled)

- Left open by phase 9: reason codes shared by the generation gates and the readiness check (the 409s still use
  English text); a way to show the hidden guide again; job-description keyword coverage; unsupported sentences
  highlighted in the preview; inferred skills become questions, not facts
- Immutable evaluation revisions; the viewed/decision record bound to a report revision
- Field-level provenance for profile facts; optimistic locking for concurrent profile edits
- Separate minimum data requirements for discovering jobs, personalized matching and generation

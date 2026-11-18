# ADR-016: Generated documents are fact-checked against the profile

Date: 2026-11-04
Status: Accepted

## Context

The prompts forbid invented facts, but afterwards the only grounding check was on numbers, and it counted numbers
from the job posting as known. A résumé could say "5+ years" because the posting did, or list a skill, employer or
title the candidate never had, and nothing noticed. `evidence_notes` from the model were free text that nothing read.
A document is the one output the user sends to an employer, and there are only a few per job picked, so a second look
is cheap compared with scoring every job.

## Decision

- **Rules first (`core/document_checks.py`).** A résumé's numbers must come from the profile alone; a cover letter may
  also use the posting's. A role heading under an experience section whose employer and title are both absent from
  the profile is a violation (one retry, like placeholders). Skills in a Skills section that appear nowhere in the
  profile are one warning. The role check is a heuristic on headings (generic headings such as "Key achievements" are
  skipped).
- **Then a model check.** `audit_document` (temperature 0) lists the factual claims of the final draft and marks each
  `supported`, `inferred` or `unsupported`, with the profile path and quote. Unsupported claims earn at most one
  targeted rewrite listing them; the new draft is kept only if it has fewer unsupported claims and no new violations.
  What remains is stored in `evidence_map.claims` and as warnings ("Not supported by your profile: ..."); the job page
  has a "Fact check" list.
- **Grounded, not timid.** The checks stop invention, not strength. The writers argue for the candidate: their brief is
  the fit reason, the strengths and the requirements not met (so they neither claim nor name them), never the score,
  recommendation or risk flags. A draft that points at a gap or hedges ("although I", "familiar with") earns the same
  one retry as a placeholder, and an unsupported claim is first restated from profile facts, removed only when none
  supports it. Measured on 4 real postings and two profiles with the live model (2026-11-14): letters used 4 to 10
  of the profile's numbers instead of 2 to 6, every résumé gained a positioning summary, and no document named a gap.
- **Never blocks.** A failed audit (quota, provider error) saves the document with `evidence_map.audit.status:
  "skipped"` and a warning that the fact check could not run. Nothing here blocks saving.
- **Models by task.** `llm.document_model` and `llm.audit_model` (both optional, default `llm.model`) let a stronger
  model write and check documents while the cheaper one still scores every job. `llm.audit_documents: false` turns the
  check off. The evidence map records the writing model, `prompt_version` and the audit model.
- **Profile hygiene.** Skills that profile synthesis adds from raw text now match whole words only ("aws" no longer
  matches "laws").

## Measured

`scripts/factcheck_eval.py` (2026-11-16) audits hand-written documents about the fictional demo candidate, each mostly
true to the profile with one or two planted false claims, in two sets. **Blunt**: 20 documents (10 résumés, 10 letters),
31 wholly invented facts over eight types (employer, title, number, certification, skill, degree or school, dates,
achievement). **Subtle**: 12 documents (6 and 6), 21 real facts bent: a profile skill credited to the wrong employer,
a bigger number or scope ("leads a team" for "mentors", "across the whole company"), shifted dates, an inflated title
("Lead", "Senior"), the right degree or certificate with the wrong school or year, one project's result on another, and
profile tools combined into work the profile never describes. A planted claim counts as caught when an audit claim
marked `unsupported` names it; a false flag is any other claim marked `unsupported`.

| Model | Set | Planted claims caught | Documents fully caught | False flags | Median s per audit | Tokens in / out |
|---|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | blunt | 31 of 31 (every type) | 20 of 20 | 0 of 118 | 1.7 | 39.6k / 11.1k |
| `gemini-3.8-flash` | blunt | 31 of 31 (every type) | 20 of 20 | 0 of 165 | 11.1 | 39.6k / 30.6k |
| `gemini-3.5-flash-lite` | subtle | 19 of 21 (90%) | 10 of 12 | 0 of 79 | 1.7 | 23.6k / 7.1k |
| `gemini-3.8-flash` | subtle | 21 of 21 (every type) | 12 of 12 | 0 of 104 | 10.8 | 23.6k / 18.8k |

The cheaper model's two misses were both inflation it called `supported` with the true fact as the quote: "Leads a
team of two junior developers" (the profile says mentors) and "lead engineer on the reporting API" (the profile says
owns). It caught every misattribution, date, credential, swapped and combined claim. Both models marked the soft
skills that follow from the profile ("communicates well across teams") as `inferred`, not `unsupported`, and neither
flagged a true claim. The larger model lists more claims per document and takes about six times as long with two to
three times the output tokens. `llm.audit_model` stays unset (the default `llm.model`): two misses in 21 from one test
author do not yet justify a slower audit on every document. Limits: 32 documents, one author, one profile, one run per
model at temperature 0; the keywords that tie an audit claim to a planted one were written by the same author.

## Consequences

- A document costs two to four model calls instead of one to two (rewrite, audit, and at most one rewrite plus audit
  again), and each call uses one daily Gemini unit.
- `responseSchema` is not used: the schema is in the prompt and the reply is validated (an unusable reply is an
  invalid-output error and is retried once), as for every other call. Moving to `responseSchema` needs a live test.
- Not done: JD keyword coverage, highlighting unsupported sentences in the preview, and turning code-inferred skills
  into questions instead of facts.

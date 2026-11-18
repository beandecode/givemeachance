# ADR-019: Score jobs from their full description only

Date: 2026-11-14
Status: Accepted. Replaces the "score the preview, cap the confidence" rule of phase 6 (docs/api.md).

## Context

Adzuna's search API returns only a short preview of each posting (about 500 characters) and has no endpoint for one
ad. Jobs found by a search were therefore scored from the preview, with the model told so; pasting the full posting
was the only way to fix that, and in practice it rarely happened. A hand-labelled set of real postings
(phase 11: 48 collected, 47 labelled) showed what this cost: only 1 of 48 previews names the years of experience a role asks for (read by the app's own
parser, `core/posting_years.py`), against 39 of 48 full postings, and the scorer's level rating separated "fits" from "too senior" far less well on previews.

## Decision

- **Read the full text from the job board's own detail page.** The ad's `redirect_url` opens Adzuna's detail page,
  which carries the whole posting as schema.org `JobPosting` data (the markup job sites publish for search engines).
  `core/job_fulltext.py` reads that block: one page per job, only on the job board's own hosts (a page that leaves
  them is ignored), 15-second timeout, text capped at 10,000 characters, one log line per page like any provider call.
- **When.** During a search, for every posting that passed the level and filter checks, before filters, relevance,
  storage and scoring see it (`adapters/jobs/adzuna_api.py`). Again before scoring any job still stored as a preview
  (older jobs, or a page that failed during the search), with the write lock released (`core/evaluate.py`).
- **No score from a preview.** A job whose full text cannot be read is not scored. It stays in the Not scored view;
  search and re-score results count it (`not_scored_no_description`, `needs_description_count`), and the job page
  asks for the posting to be pasted.
- **Attribution.** Adzuna's API terms ask that every listing it supplies be labelled "Adzuna" with a link to its site:
  job rows, the job page and the Discover side panel show "via Adzuna" / "Jobs by Adzuna".

## Consequences

- A search takes about a second longer per new job; no extra AI calls and no extra job-board quota.
- This reads web pages outside the API. Adzuna's API terms do not address it and allow personal job search; the volume
  is the same as a person opening each ad. If the job board blocks it, jobs simply wait for a pasted description.
- With full text, the level rating's agreement with the hand labels rose from 0.68 to 0.79 to 0.83 across runs
  (the share of "fits / too senior" pairs ranked the right way round). See the README for the measured results and
  `scripts/labelling.py report` for the intervals.

## Model comparison (2026-11-16)

Four models score the same 48 full postings with the same prompt (v3) and profile; `scripts/labelling.py report`
prints the numbers. Agreement is measured on the 47 labelled postings (46 for `gemini-3.8-flash`, whose one invalid
JSON response is left out). Prices are Google's paid-tier rates of the same day; `gemini-3.8-flash` is an introductory
rate until 2026-12-31 and doubles after.

| Model | Level agreement (95% interval) | Apply above skip (95% interval) | Fitting roles in the deck | Seconds per posting | Cost per 100 postings |
|---|---|---|---|---|---|
| `gemini-2.5-flash-lite` | 0.74 (0.60 to 0.86) | 0.60 (0.34 to 0.84) | 14 of 17, but 4 skip-labelled roles too | 2.4 | $0.06 |
| `gemini-3.5-flash-lite` (used) | 0.83 (0.70 to 0.93) | 0.76 (0.56 to 0.92) | 7 of 17, no skip-labelled role | 1.9 | $0.24 |
| `gemini-3.8-flash` | 0.81 (0.67 to 0.92) | 0.88 (0.71 to 0.99) | 4 of 16, no skip-labelled role | 10.6 | $0.72 |
| `gemini-4-hydrogen` | 0.79 (0.65 to 0.91) | 0.80 (0.59 to 0.96) | 2 of 17, no skip-labelled role | 14.4 | $2.46 |

- The intervals overlap: 47 postings cannot separate the three newer models, so the choice rests on speed and cost.
  `gemini-3.5-flash-lite` is 5 to 8 times faster and 3 to 10 times cheaper than the two larger models for the same level
  agreement.
- The older model puts four roles the labeller would skip into the deck (next to 14 fitting ones); the newer ones put none there. The larger
  models are stricter, so fewer fitting roles reach the deck at a score of 70.
- `gemini-3.8-flash` returned one response that was not valid JSON in 48 calls (the others none).
- Fact-check models are compared in [ADR-016](ADR-016-grounded-documents.md#measured).

# ADR-017: A cheap funnel in front of the AI score

Date: 2026-11-04
Status: Accepted

## Context

Every new job cost one AI call. The only filter in code was the title's level. When a search was limited
(`score_limit`) the jobs scored were the first N in the order the job board returned them, not the most relevant.
Skipping a job taught the app nothing, so the same kind of job kept coming back.

## Decision

- **Hard filters in code** (`core/job_filters.py`, applied in `core/ingest.py` next to the level filter, before a
  posting is stored or counted): a stated maximum salary below the minimum; title words the user excludes (whole
  words); work modes (`remote`, `hybrid`, `onsite`) read from the posting; and "knockouts" the posting plainly states
  (security clearance, citizenship required, no sponsorship). A posting that does not say something passes: unknown
  work mode or salary is never a reason to drop it. Job boards send only a preview of each posting, so a requirement
  further down the text is not seen. The task result reports `skipped_by_filters` per filter.
- **A relevance pre-score** (`core/prefilter.py`, 0 to 100, no AI call): the target roles' words in the title (50), the
  profile's skills in the title and preview (40 plus 10 for a skill in the title). It is stored on `jobs.relevance`
  (migration 0011) when a search saves the jobs, and decides which jobs a limited search scores first and in what order
  "Score all" and the "Not scored" list take unscored jobs. It ranks; it never rejects. Embeddings are not used (no new
  dependency, [ADR-005](ADR-005-product-fit-and-growth-triggers.md)); revisit if relevance proves too crude.
- **Skip reasons feed suggestions.** A skip can carry one optional reason (`too_senior`, `too_junior`, `wrong_field`,
  `location`, `pay`, `other`; `job_triage.reason`). Three or more of the same reason become a suggestion
  (`GET /api/v1/search-suggestions`): stop searching the highest level in use, or exclude a title word that appears in
  at least two of the skipped jobs and is not in the profile. Suggestions are shown in the search sheet and applied only
  when the user presses Apply.
- **Calibration.** `scripts/calibration_report.py <username>` prints the lowest, median and highest match score for each
  outcome (accepted, waitlisted, skipped, applied, interview, offer), to choose the Discover threshold.

## Consequences

- Filters and relevance cost nothing per job; a search that filters well makes fewer AI calls.
- Not done, on purpose: several locations or keyword sets per search (each Adzuna request counts against a small daily
  quota, so breadth would exhaust it), scheduled per-user searches (nothing schedules a search) and automatic archiving of old jobs (it would change the user's data silently).
- Suggestions have no "dismiss": once applied they disappear; until then they stay.

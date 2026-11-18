# ADR-014: The user controls how many jobs are fetched and scored

Date: 2026-10-25
Status: Accepted

## Context

One click on "Search job board" used to fetch jobs and score every new one: one AI call each, up to the per-run cap
(20 in the main config, 5 on localtest), with retries costing extra quota. The user could not choose, could not see
what happened, and when the daily quota ran out the remaining jobs were saved unscored while the task still reported
"Search finished". "Re-score" skipped jobs that had never been scored (its queries joined `evaluations`), so a job
without a score could not be scored later. A fetch cap of N also counted duplicates, so "fetch 5" could add nothing.

## Decision

- **Options on the search request:** `fetch_limit` (1 to 500; null or above the server cap means the cap) and
  `score_limit` (0 to 500; null scores every new job, 0 fetches only, N scores the first N in the order the board
  returned them). `{}` keeps today's behaviour, so a plain click still fetches and scores.
- **`fetch_limit` counts new jobs.** Postings the user already has are rejected inside the adapter's `accept` hook, using
  the same duplicate rules as the insert (`core/repositories/jobs.py:job_already_saved`), so duplicates never use the
  limit up. `pipeline.daily_limit` is a per-run cap despite its name; `/api/v1/config` reports it as
  `search_results_per_run` (it used to be a hard-coded 10).
- **Quota stops scoring.** A dedicated `QuotaExhaustedError` (raised by the Gemini adapter) ends the evaluation loop at
  the first exhausted daily quota instead of failing every remaining job; the jobs not tried are reported. The task
  still succeeds, because the fetched jobs are saved, but the result says so.
- **Honest results:** the task result reports what was fetched, skipped (by level, as duplicates), scored and left
  unscored (by choice, by quota, failed). The web app turns this into a sentence.
- **One search at a time per user** (`EXCLUSIVE_TASK_TYPES` in `core/task_service.py`): a second search with different
  options would double the job-board requests; the identical request still returns the running task.
- **Scoring later:** re-scoring accepts jobs without a score (`scope: "unscored"` and explicit `job_ids`), which also
  fixes "Score this job" on an unscored job.

## Consequences

1. The Jobs page gets a search sheet (parameters leave Settings, options and a cost estimate appear), a Not scored view
   and Score actions; these arrive in the following commits.
2. Estimates must include the job-board quota (one request per keyword) and say that retries can use a few more AI
   calls; mock providers use no quota and demo limits are 0.
3. Cancelling a search mid-scoring keeps the jobs already scored and produces no summary.

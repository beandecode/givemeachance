# ADR-015: The guided journey is computed on the server

Date: 2026-11-04
Status: Accepted

## Context

A review of the flow found dead ends: a new user with no jobs saw "you have decided on every job" on Discover; a user
with an unapproved profile skipped onboarding; "Write my résumé" stayed clickable on an out-of-date match and the server
then answered 409; nothing was suggested after "Applied"; onboarding copy pointed at a Settings page that no longer
holds search options. Each screen decided for itself what to offer, from partial data.

## Decision

- **One source of truth.** `core/journey_service.py` derives every step from stored data (profile readiness, saved search
  settings, jobs and scores, swipe decisions, documents, applications). Nothing about progress is stored, so the guide
  cannot disagree with the data. The only stored value is the "hide the guide" flag, a `journey` row in
  `user_preferences`.
- **Two scopes.** `GET /api/v1/journey`: the account steps (profile, search settings, find jobs, pick jobs, write a
  résumé, apply), the current one, counts, and `discover`, the reason the Discover deck is empty (`has_cards`,
  `no_jobs`, `none_scored`, `below_threshold`, `all_decided`). `journey` on `GET /api/v1/jobs/{id}`: score, write,
  review, apply, follow up for that job. The first step that is not done is the current one; the review step never
  blocks the next one, because document warnings are advice.
- **Reason codes, not sentences.** Steps carry stable `reason_code`s (`profile_not_approved`, `match_stale`,
  `no_follow_up`, ...) and a call-to-action label and route. The web app owns the copy (`journeyCopy.ts`).
- **First run is a wizard, afterwards a bar.** Onboarding grows from three to six steps (background, check profile,
  search settings, find jobs, pick jobs, first résumé) and resumes from the server state. After setup, a quiet bar in
  the shell shows the current step until the first application; the user can hide it. The job page shows its own five
  steps and offers only the action that fits the current one, so a stale match offers "Re-score" instead of a button
  that would fail.
- **Follow-ups.** Applications gain `follow_up_at` (migration 0010). Setting it is a `PATCH` on the application with
  `follow_up_at` (`null` clears it); the board marks overdue follow-ups on submitted and interview applications.

## Consequences

- Every mutation and finished task invalidates the journey query in the web app, so the guide follows the data.
- Not done yet: the generation gates still return English 409 messages; sharing the reason codes with them (and the
  readiness check) is a follow-up. "Re-score and write" is two clicks (re-score, then write), not one queued chain.
- The hidden guide has no way back yet other than `PUT /api/v1/journey {"skipped": false}`.

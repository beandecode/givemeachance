# ADR-013: Job triage state, user preferences and the swipe deck

Date: 2026-10-25
Status: Accepted

## Context

After a search, scored jobs pile up in a list. The goal is a Tinder-style screen to decide quickly: by default
swipe right to write a résumé, left to skip, up to put the job on a waitlist, down to open the details; every
direction is remappable. The deck shows only jobs at or above a score threshold. Today there is no "decided / skipped /
waitlisted" concept (only `jobs.archived_at` and `generation_decisions`) and no general per-user preference storage
(only `user_search_preferences`). The application board has eight stages (`draft` to `withdrawn`) that must not change.

## Decision

- **Triage is its own state.** Table `job_triage(user_id, job_id, action, generate, decided_at)`, primary key (`user_id`,
  `job_id`), with `action` in `skipped`, `waitlisted`, `accepted` and `generate` (`resume` or `resume_and_cover_letter`, set
  with `accepted`, so a queued request survives a reload). No row means "pending". It is separate from the
  application stages and from archiving, so skipping is reversible and the board is untouched. `accepted` means the
  user asked for a résumé; the document itself still follows the existing generation gates and decision record.
- **API** (`/api/v1`, typed, owner-scoped, 403 in demo mode):
  `PUT /jobs/{id}/triage {action, generate?: "resume" | "resume_and_cover_letter"}` records the action and, for
  `accepted`, submits the generation task through `submit_task` outside any write transaction; the response includes
  the task or `queued_for_later` when the per-user active-task limit (3) is reached. `DELETE /jobs/{id}/triage` is
  undo and cancels a task that has not started. `GET /jobs` gains `triage=pending|skipped|waitlisted|accepted`
  (deck = `pending` plus `min_score`, sorted by score). `GET`/`PUT /preferences` read and write the typed model below.
- **Preferences:** table `user_preferences(user_id, key, value_json)` holding three JSON sections (`swipe`, `deck`, `ui`) behind one
  typed `UserPreferences` model validated on write; unknown keys are rejected. `swipe.left|right|up|down` take `skip`, `generate_resume`, `generate_resume_and_cover_letter`, `waitlist`, `details`,
  `none` (defaults `skip`, `generate_resume`, `waitlist`, `details`; the four must be distinct unless `none`),
  `deck.min_score` (0 to 100, default 70), `deck.mouse_drag` (default on), `deck.buttons` (default on),
  `ui.glass` (`auto` default, see ADR-012).
- **Input:** touch swipe and arrow keys are always on; mouse drag and the on-card buttons are switchable. With buttons
  off, a visually hidden but focusable action list remains for screen readers and keyboard users.
- **Queued generation:** swiping right on a fourth job while three tasks run stores `accepted` and shows it as
  waiting; the client starts the next accepted job without a résumé as slots free. After a reload the queue is
  re-derived from `triage=accepted` and "no résumé yet", so nothing is lost.
- **Gestures without a library:** an in-house `useSwipe` hook on Pointer Events with CSS transforms set through the
  CSSOM (CSP-safe): the dominant axis decides the direction once past a distance or velocity threshold, the card
  rubber-bands back otherwise, and the fly-out honours `prefers-reduced-motion`.
- **Screens:** primary navigation is Discover (the deck, home after onboarding), Jobs, Applications, Profile. The
  jobs list gains Waitlist and Skipped views; a waitlisted job can return to the deck.

## Consequences

1. Migration 0009 adds both tables; repositories, `core/triage_service.py` and `core/preferences_service.py` own the
   queries; routes live in `app/route_groups/`; the OpenAPI file and generated web types are regenerated.
2. Tests cover transitions, undo, owner scoping, the task limit and queueing, preference validation (duplicates,
   unknown keys), the demo-mode write sweep and the writer-lock probe.
3. The deck's empty state names the threshold and offers to lower it or run a search.
4. Further preference keys are added to the typed model, never as free-form JSON.

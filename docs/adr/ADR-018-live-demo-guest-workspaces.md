# ADR-018: Live demo with guest workspaces (`DEMO_LIVE`)

Date: 2026-11-12
Status: Accepted. Extends [ADR-009](ADR-009-read-only-demo-mode.md): the read-only sample workspace stays as it is;
its rule "mock providers and zero quota" now applies only while `DEMO_LIVE` is off.

## Context

The read-only demo shows finished results but not the product working: a visitor cannot search, score a posting or
get a document written. Opening a personal instance, or simply switching the demo to real providers, would let
strangers spend the operator's quota, store their personal data and change what the next visitor sees.

## Decision

- **Two workspaces in one demo instance.** Without a session a visitor reads the seeded sample workspace exactly as
  before (reserved `demo` user, every write refused). `POST /api/v1/demo/guest` creates a throwaway account
  (`guest_<random>`, no usable password) and signs the visitor in to it.
- **A guest starts from the sample profile.** The demo user's approved profile and search settings are copied; the job
  list starts empty. Guests cannot upload their own résumé, edit the profile by hand, sign in or sign up, so no
  visitor's résumé is stored.
- **The sample profile is complete** (`data/mock/demo_profile.json`: titles, dates, numbers, education, preferences),
  because guests are scored with it by the real model: on 16 real backend and data postings the median score rose from
  36 to 59 over the earlier thin profile, which left the model guessing years and dates.
- **Résumé input is tried on a sample (added 2026-11-15).** A guest may rebuild the profile from a fictional sample
  résumé in any format the app reads (`data/mock/sample_resume/`: text, PDF, Word, PNG, made by
  `scripts/make_sample_resumes.py`), approve it and answer its gap questions. `POST /api/v1/profile/synthesize` from
  a guest must name a `sample` and ignores everything else in the body; the request text of a gap answer is the only
  free text, like a pasted job description, and is deleted with the guest. The sample leaves a few details out on
  purpose (co-op dates, project results) so the questions are real.
- **Writes by allowlist.** In demo mode the write guard lets a guest call only `GUEST_WRITE_ENDPOINTS`
  (`core/demo.py`): search, paste a job, score, triage, generate and edit documents, application status, own settings,
  leave. A test fails when a new write route is in neither the allowlist nor the refused list.
- **Bounded spending.** Guests use the real providers through the existing quota system: per-guest and global daily
  limits (`config/settings.demo-live.yaml`: 25 and 100 AI calls, 3 and 30 job-board calls, five new jobs per search).
  Startup fails unless the global limits are between 1 and 500 and the per-guest limits do not exceed them. When a
  limit is reached the usual quota message is shown; the sample workspace keeps working.
- **Bounded growth.** At most 40 guests are created per 24 hours (`DEMO_GUESTS_PER_DAY`) and at most 5 from one
  address (`DEMO_GUESTS_PER_CLIENT`; the app counts starts per keyed hash of the address in `guest_starts` and never
  stores the address itself, so no rate limit at the edge is needed); a guest and everything it
  owns is deleted after 24 hours, the next time a guest is created. The database is on tmpfs and re-seeded on every
  start. A deleted guest's browser falls back to the sample workspace.
- **Sessions need a real key.** The live demo refuses to start without a strong `FLASK_SECRET_KEY` (guest sessions
  must be valid on every worker). The sample workspace is still seeded with mock providers
  (`config/settings.demo.yaml`) before the server starts with the live settings on the same database.
- `GET /api/v1/config` adds `demo_live` and `guest`; `demo_mode` is false for a guest, so the web app's read-only
  behaviour switches off without further changes. The banner offers "Try it live" and "Back to the sample workspace".
- **First-visit tour.** A visitor's first look at the sample workspace opens a short guided tour (`web/src/features/tour/`)
  that ends on the "Try it live" button; it is remembered in local storage and can be restarted from the banner.

## Consequences

- The public demo container now holds provider keys. The spend is capped per day by configuration.
- The per-address limit relies on `TRUSTED_PROXY_HOPS` matching the proxies in front of the app; visitors behind one
  shared address (an office) share its five starts a day.
- Job descriptions pasted by guests are sent to the AI provider and kept for at most 24 hours; they are visible only
  to that guest.
- One guest can use up to a quarter of the day's AI budget; visitors after the budget is spent get the read-only demo.

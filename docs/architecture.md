# Architecture

Current-state description of how the system is built. For planned changes see [roadmap.md](roadmap.md);
for the reasoning behind major choices see [adr/](adr/).

## Overview

GivemeaChance is a **modular monolith** ([ADR-001](adr/ADR-001-modular-monolith-first.md)):
one Flask process, SQLite storage, and adapters for external providers.

```
Browser ── React app (/app, web/) ─── /api/v1/* ───┐
                                                   ▼
                     app/route_groups/*  (typed routes, guards)
                                                   ▼
                     core/*  (services, gates, task handlers)
                     │                    │
                     ▼                    ▼
         SQLite (core/db, core/repositories)   adapters/jobs/*, adapters/llm/*
                                    (Adzuna | mock)  (Gemini | mock)
```

Long-running work (search, evaluation, generation) can run as async tasks on an in-process
thread pool (`core/async_tasks.py:LocalTaskRunner`, 2 threads per process) with state persisted in SQLite.

Product principles: profile quality is central; generation always sits behind an explicit human
decision; provider usage is quota-limited; every user's data is isolated by owner.

## Code map

| Area | Files | Responsibility |
|---|---|---|
| App factory | `app/__init__.py`, `run.py` | Load settings, require `FLASK_SECRET_KEY`, `init_db`, admin bootstrap, register routes |
| HTTP (system) | `app/routes.py` (composition only), `app/route_groups/system.py`, `app/guards.py`, `app/http.py` | Health/readiness, OpenAPI document, write-auth and request-boundary guards, correlation IDs |
| HTTP (`/api/v1`) | `app/api.py` (`api_route`, envelope, error handlers), `app/api_models.py` (request/response models), `app/openapi.py` (document builder), `app/route_groups/{workspace,api_jobs,api_documents,api_profile}.py` | Typed JSON contract ([ADR-006](adr/ADR-006-typed-api-layer.md)); every route lives in `app/route_groups/` so the route inventory sees it |
| Web app | `web/src/` (see [Web app](#web-app)), `app/route_groups/spa.py` (serves the build at `/app` and the static case study in `app/case_study/` at `/case-study`) | React SPA on the `/api/v1` contract ([ADR-008](adr/ADR-008-react-spa.md)) |
| HTTP policy | `app/guards.py`, `app/http.py` | Correlation IDs, write-auth guard, cross-origin write rejection, JSON/body limits, error responses |
| Identity | `core/users.py`, `core/request_context.py`, `core/user_scope.py`, `core/login_throttle.py` | Users/passwords, session → user resolution, admin/owner scope helpers, per-username sign-in throttling |
| Profile | `core/profile_input_service.py`, `core/profile_synthesis.py`, `core/profile_quality.py`, `core/profile_readiness.py` | Input/attachment validation, LLM synthesis & supplement, completeness scoring, readiness gate |
| Jobs | `core/seniority.py`, `core/ingest.py`, `core/evaluate.py`, `core/re_evaluation_service.py`, `core/search_preferences.py`, `core/job_service.py`, `core/triage_service.py`, `core/preferences_service.py`, `core/job_text.py`, `core/posting_years.py`, `core/scoring.py`, `core/evaluation_profile.py`, `core/journey_service.py`, `core/job_filters.py`, `core/prefilter.py`, `core/suggestions_service.py`, `core/calibration.py` | Fetch + dedupe jobs, fit evaluation, scoped re-evaluation, per-user and suggested search config, job list/detail/archive reads (with the years of experience a posting asks for, read from its text on every read), swipe triage (skip / waitlist / accept → documents), typed UI preferences, the guided journey state ([ADR-015](adr/ADR-015-guided-journey.md)), hard search filters, the relevance pre-score, search suggestions from skip reasons and the score calibration report ([ADR-017](adr/ADR-017-search-funnel.md)) |
| Generation & export | `core/generation_service.py`, `core/document_generation.py`, `core/document_checks.py`, `core/generate_resume.py`, `core/generate_cl.py`, `core/export/{blocks,pdf,docx}.py` + `core/export/fonts/` | Decision/version gates, resume & cover-letter generation, PDF/DOCX export ([ADR-007](adr/ADR-007-pure-python-export.md)) |
| Tasks | `core/async_tasks.py`, `core/task_service.py`, `core/task_handlers.py`, `core/profile_tasks.py`, `core/task_contracts.py` | Task table, guarded transitions, heartbeat/recovery, runner; `submit_task` (validation, capacity, enqueue); per-type handlers; payload models |
| Read models | `core/workspace_service.py` (for `/api/v1`) | Assemble view data |
| Data | `core/db/{connection,migrations}.py`, `core/repositories/*.py`, `core/persistence.py`, `core/api_limits.py` | Connections, schema migrations, data access per aggregate, visibility clauses, quota counters |
| Config | `core/config.py`, `core/schemas.py`, `config/*.yaml` | Cached settings loading (env overrides), pydantic models |
| Demo | `core/demo.py`, `core/guest_service.py`, `scripts/seed_demo.py`, `scripts/make_sample_resumes.py` + `data/mock/sample_resume/` | `DEMO_MODE` flag, startup safety check (mock providers and zero quota, or bounded limits when live), deterministic sample workspace ([ADR-009](adr/ADR-009-read-only-demo-mode.md)); `DEMO_LIVE` guest workspaces on real providers, profiles built from a sample résumé ([ADR-018](adr/ADR-018-live-demo-guest-workspaces.md)) |
| Shared helpers | `core/logging_setup.py`, `core/errors.py`, `core/parsing.py`, `core/request_normalization.py`, `core/time_utils.py` | User-facing vs internal errors, JSON-or-text column parsing, lenient request-input parsing and user-details normalization, UTC time |
| Providers | `adapters/jobs/{adzuna_api,mock_adzuna,mock_jooble}.py`, `core/job_fulltext.py`, `adapters/llm/{gemini_api,mock_gemini}.py`, `core/llm_prompts.py` | External calls and prompts |
| Scripts | `scripts/` | Route inventory, OpenAPI export, doc-drift check, browser-test server (`e2e_web_server.py`), demo seed, calibration report, labelling tool, deploy wrappers |

## Main flows

1. **Profile synthesis** — `POST /api/v1/profile/synthesize` (JSON; PDFs/images as base64; a Word `.docx` is read
   to text with python-docx, so its text joins the pasted résumé) → validate input → task: LLM builds a Master Profile
   → stored as a new **pending** version in `candidate_profiles`. Uploaded files are not kept, only their names.
   - What the candidate typed in the form wins over what the model read; dates are never estimated.
   - Entries that are one thing (a bullet, a degree, a credential) are never split; only an entry that reads as a list
     ("Python, SQL") is.
   - The profile serves any occupation: `skill_matrix` has `professional_skills` and `tools` next to the technical
     groups, which stay empty for other fields.
2. **Profile supplement** — `POST /api/v1/profile/supplement` answers missing fields → new pending version
   (old versions are never edited in place). The model gets the whole current profile, hand edits included, and code
   then puts back any role, bullet or list item it dropped (`_keep_previous_facts`). An answer whose field names a
   position (`experiences[1].achievements`, `projects[0].impact`, `experiences[1].start_date`) lands on that entry,
   matched by title and company if the model reordered them: dates as dates, anything else as a result bullet.
3. **Review** — `POST /api/v1/profile/{id}/review` marks a version `approved` or `needs_changes`.
4. **Search** — search task (`POST /api/v1/searches`): readiness gate → fetch from provider → read each accepted
   posting's full text ([ADR-019](adr/ADR-019-full-job-descriptions.md)) → dedupe insert into `jobs` → evaluate the new jobs against the latest profile → `evaluations`. The caller chooses how many new jobs to
   fetch (`fetch_limit`, at most `pipeline.daily_limit`, which is a per-run cap despite its name; duplicates do not count) and
   how many to score (`score_limit`; 0 = fetch only); scoring stops at the first exhausted daily quota
   ([ADR-014](adr/ADR-014-user-controlled-search-and-scoring.md)).
   Pasting a single JD (`manual_jd_match`) inserts and evaluates one job.
   Which jobs get that far is the user's choice of levels (`core/seniority.py`): titles of unselected levels are
   filtered out inside the adapter loop, so a search still tries to fill its limit. The suggested levels are wide on
   purpose (one either side of the candidate's years, internships not counted), titles without a level word are always
   kept, and "Account Manager" or "Case Manager" counts as an individual role, not management.
5. **Generation** — `POST /api/v1/jobs/{id}/documents` records "viewed match" and the decision, then a task generates
   the resume or cover letter (LLM rewrite) → versioned rows (edits by the user become new versions with `origin = edited`).
   - The writers work for the candidate: their brief is the fit reason, the strengths and the requirements not met
     (so they neither claim nor name them), never the score or the risk flags.
   - Rule checks (`core/document_checks.py`) give one retry with the problems listed: placeholders, a role at an
     employer not in the profile, phrases that point at gaps or hedge, and for a letter a missing company name or
     signature, stock phrases, or a length outside 180 to 450 words.
   - A model fact check (`audit_document`) links each claim to a profile fact; unsupported claims get one targeted
     rewrite. What remains is shown as warnings and in a Fact check list; nothing blocks saving
     ([ADR-016](adr/ADR-016-grounded-documents.md)).
6. **Export** — `core/export/`: Markdown → blocks (markdown-it-py) → PDF (fpdf2, bundled DejaVu Sans fonts,
   US Letter) or DOCX (python-docx, Word heading/list styles). Pure Python, no system libraries.
7. **Tracking** — `PATCH /api/v1/jobs/{id}/application` with `draft | ready | submitted | interview | offer | hired | rejected | withdrawn`.

## Gates and invariants

- **Write auth** — all `POST/PUT/PATCH/DELETE` except auth endpoints need a real login; the demo user is read-only; in the live demo a guest may use an allowlist of write endpoints.
- **Owner scope** — every `/api/v1` read and write is limited to the caller's own jobs, profiles, tasks and documents
  (`job_visibility_clause`), admins included.
- **Readiness gate** — search and re-evaluation require the *latest* profile version to be approved and
  have completeness ≥ 70 (`core/profile_readiness.py`). `force_when_high_missing` only bypasses
  missing *core* fields (exactly `identity.name`, `core_skills` and an empty `experiences` list; questions about parts of an entry never block) on an approved profile.
- **Pasted-job gate** — adding a single pasted job description only needs the *minimum* (an approved profile with a name, at least 3 core skills and one experience; `minimum_ready` in the readiness result), not the completeness score or the high-priority question count. The error lists the missing pieces.
- **Completeness score** — computed by the application, never taken from the model
  (`core/profile_quality.py`, source `application_field_coverage_v1`). Weights: name 15, skills 20,
  experience 25, education 10, certifications 10, projects 5, evidence notes 5, links 5, target roles 5.
  It measures field coverage only — not truthfulness or hiring probability.
- **Decision gate** — generation needs `viewed_match_at` plus a decision for that document type.
- **Version consistency** — the profile used for generation must be the one the evaluation was made from, or one
  the scorer cannot tell apart from it: each evaluation stores a fingerprint of what the scorer saw
  (`core/evaluation_profile.py`, migration 0007), so correcting a name, e-mail or phone number keeps matches valid
  while a change to skills, experience, level or preferences gives 409 (re-evaluate first). Saving a new evaluation
  clears the viewed flag and generation decisions in the same transaction.
- **Application status** — auto-marking "ready" only moves `draft → ready`; it never downgrades
  submitted/interview/offer progress.
- **Full text before scoring** — a job stored only as the job board's preview is never scored: `core/evaluate.py`
  fetches its full text first and otherwise leaves it unscored ([ADR-019](adr/ADR-019-full-job-descriptions.md)).
- **Quotas** — per-user and global daily limits per provider are checked before outbound calls (`core/api_limits.py`).

## Data

SQLite file at `app.db_path` (default `output/job_assistant.db`) in **WAL** mode.

- **Connections** — `core/db/connection.py:db_conn` gives one unit of work per `with` block (commit on exit,
  rollback on error). Every connection enforces **foreign keys** and waits up to 30 s for the writer lock.
- **Migrations** — `core/db/migrations.py:init_db` runs at app start under a file lock and applies every entry of
  `MIGRATIONS` not yet recorded in `schema_migrations`: each in its own transaction, with foreign keys off during
  the change and a `foreign_key_check` before commit (a violation rolls the migration back). An existing database
  with pending migrations is first copied to `<db>.bak-<UTC timestamp>`. To change the schema, append a new
  migration function to `MIGRATIONS`; never edit one that has shipped.
- **Data access** — `core/repositories/{jobs,decisions,profiles,documents,applications,runs}.py`; callers pass an
  open connection. Cover-letter rows are still written in `core/generate_cl.py`.

| Table | Purpose |
|---|---|
| `users` | Accounts (`is_admin`, `is_active`, password hash) |
| `jobs` | Job postings, `owner_user_id` controls visibility; `relevance` is the cheap 0–100 pre-score |
| `evaluations` | Fit scores and explanations per job; `source_profile_id/version` for traceability |
| `candidate_profiles` | Versioned Master Profiles per user with review status |
| `generation_decisions` | Viewed-match ack and which documents to generate |
| `generated_resumes`, `cover_letters` | Versioned generated Markdown (`UNIQUE(job_id, version)`) with evidence map |
| `applications` | Status, note and follow-up date per job |
| `user_search_preferences` | Per-user Adzuna search config (fallback: `config/search_params.yaml`) |
| `job_triage` | Swipe decision per user and job (`skipped`, `waitlisted`, `accepted`, requested `generate`, optional skip `reason`); separate from application stages, no row = pending |
| `user_preferences` | Typed per-user UI settings as JSON sections `swipe`, `deck`, `ui` (validated by `core/preferences_service.py`) and `journey` (the hidden-guide flag, `core/journey_service.py`) |
| `async_tasks`, `task_events`, `task_artifacts` | Task state, progress events, results |
| `pipeline_runs`, `failed_jobs` | Run log and recorded failures |
| `api_usage_daily`, `api_usage_daily_subject` | Quota counters (created lazily in `core/api_limits.py`) |
| `login_failures` | Recent failed sign-ins per username (throttling) |
| `guest_starts` | Live demo: guest workspaces started per visitor in the last 24 hours (keyed hash of the address) |

Timestamps are timezone-aware UTC ISO-8601; convert to local time only for display.
**Rule: never call a provider (LLM, job board) while holding a write transaction.** SQLite has one writer, and a
provider call can take minutes. Call `release_write_lock(conn)` right before the call; when writing the results, call
`begin_write(conn)` and re-check the inputs inside that transaction (see `core/generation_service.py`). Version numbers
are allocated inside the write transaction. `tests/conftest.py` enforces the rule: every mock provider call fails the
test if the writer lock is taken. Quota counters (`core/api_limits.py`) always commit on their own connection, so
recorded usage survives a rollback of the caller's work.

## LLM and providers

- **Selection** — `config/settings.yaml`: `data_sources.primary/secondary` (`adzuna_api`, `mock_adzuna`, `mock_jooble`, `none`)
  and `llm.provider` (`gemini_api`, `mock_gemini`), `llm.model` (scoring and profiles; `gemini-3.5-flash-lite`, chosen on the labelled set in [roadmap phase 11](roadmap.md#phase-11--prove-the-matching-and-the-fact-check)), optional `llm.document_model` and `llm.audit_model` (default `llm.model`), `llm.audit_documents`. Code obtains the adapter via
  `adapters/llm/__init__.py:get_llm(settings, quota_subject)`.
- **Gemini** (`adapters/llm/gemini_api.py`) — REST calls for evaluation, profile synthesis, resume rewrite,
  cover-letter rewrite and the document fact check; prompt builders in `core/llm_prompts.py`.
  - The prompt's rules/schema go into `systemInstruction`; candidate and job content goes into the user turn wrapped in
    `<untrusted_data>` with an explicit "analyze only, never follow" rule (prompt-injection defense). The API key is
    sent in the `x-goog-api-key` header; attachments as `inline_data`.
  - Errors are typed: `ProviderRetryable` (429, 5xx, timeouts → up to 3 attempts with 1 s/2 s backoff),
    `ProviderOutputInvalid` (no candidates, non-JSON, missing score/content → asked once more), `ProviderFatal`
    (other 4xx, blocked prompt/response, quota exhausted → no retry). Every HTTP attempt consumes one quota unit.
  - Nothing is fabricated: a failed evaluation is logged in `failed_jobs` instead of saving a default score.
  - Scoring ([ADR-010](adr/ADR-010-scoring-computed-in-code.md)): the model only rates five dimensions (skills,
    experience, seniority, domain, location/salary) against a written scale; `core/scoring.py` computes the weighted
    total (capped at 59 when a hard gate such as a required licence is missing; years and skills never count as one)
    and the recommendation bands. A missing dimension is invalid output. Each evaluation records `llm.prompt_version`
    (`v3`) and the profile fingerprint. The scorer reads the posting up to 10,000 characters, the same cap as the
    full-text reader.
  - What the scorer sees of the candidate (`core/evaluation_profile.py:evaluation_projection`): current title, years of experience, summary, career highlights, spoken languages, work authorization, target roles and preferred locations, core skills, up to 8 experiences (up to 10 bullets each, with the employment type), 3 projects, education, certifications and licences. Name, email and phone are never sent.
  - Placeholder values ("unknown", "N/A") are kept in stored profiles but stripped before generation
    (`core/profile_synthesis.py:without_placeholders`).
- **Adzuna** (`adapters/jobs/adzuna_api.py`) — query mapping from `JobSearchConfig`; paging fixed to
  10 results × 1 page for quota control. The API returns previews only, so the full posting of each accepted job is read
  from the job board's detail page (`core/job_fulltext.py`, schema.org `JobPosting` data); jobs are scored from full
  text only ([ADR-019](adr/ADR-019-full-job-descriptions.md)).
- **Mocks** — deterministic fixtures in `data/mock/` and `adapters/*/mock_*.py`; used by tests and `config/settings.test.yaml`.
  `MOCK_LLM_DELAY_SECONDS` (default 0) makes the mock model pause per call so browser tests can watch running tasks.
- Keys come from `config/api-keys.env` (`GEMINI_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`).

## Configuration

| Source | What |
|---|---|
| `config/settings.yaml` | Production-ish defaults (live providers) |
| `config/settings.test.yaml` | Mock providers, high limits — tests only |
| `config/settings.demo.yaml`, `config/settings.demo-live.yaml` | Read-only demo (mock providers, zero quota; also seeds the live demo) and the live demo's real providers and daily budgets |
| `config/search_params.yaml` | Default/admin search config; normal users' configs live in the DB |
| Env: `SETTINGS_FILE`, `RESUME_FILE`, `SEARCH_PARAMS_FILE` | Override config paths |
| Env: `FLASK_SECRET_KEY` (required, ≥32 chars), `SESSION_COOKIE_SECURE`, `ADMIN_BOOTSTRAP_*`, `REGISTRATION_MODE`, `DEMO_MODE`, `DEMO_LIVE`, `DEMO_GUESTS_PER_DAY`, `DEMO_GUESTS_PER_CLIENT`, `TRUSTED_PROXY_HOPS` | Runtime/security |
| Env: `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT` | Gunicorn (`gunicorn.conf.py`) |
| Env: `LOG_FORMAT` (`text` default, `json` in the Docker image), `LOG_LEVEL` (default `INFO`) | Logging (`core/logging_setup.py`) |
| `pipeline.*`, `api_limits.*` keys | Per-run job cap, description length, quota caps |

Settings are frozen pydantic models, loaded once per process on first use (`core/config.py:load_settings`); restart the process after changing config. Tests call `reset_config()` to reload and `install_settings(...)` / `patch_llm_settings` (in `tests/conftest.py`) to run with a derived copy.

## Web app

React + TypeScript single-page app in `web/`, served by Flask at `/app` ([ADR-008](adr/ADR-008-react-spa.md)).

- `src/index.css`: all design tokens (Neon Glass light/dark colours, type scale, radii, motion, glass intensity sets and the `.glass` / `.glass-plate` / `.glass-ctl` / `.hud` utilities, [ADR-012](adr/ADR-012-neon-glass-design-language.md)) in one `@theme` block; the three self-hosted fonts live in `src/assets/fonts/` (CSP `font-src 'self'`). `src/test/tokens.test.ts` checks WCAG contrast of every colour pair.
- `src/api/`: `schema.d.ts` is generated from `docs/openapi.json` (`npm run gen:api`, never edit by hand);
  `client.ts` (typed `openapi-fetch` client, `unwrap()` returns the envelope's `data` or throws `ApiError`),
  `errors.ts` (error code → human message + reference), `queries.ts` (query keys and shared hooks).
- `src/features/<area>/`: `auth` (sign-in, route guard), `shell` (layout, navigation), `tasks` (task provider:
  follows, polls and reports background tasks; tray; progress bar), `discover` (swipe deck: `useSwipe` pointer-event drag, `SwipeCard`, optimistic decisions with undo, queued
  generation), `jobs` (list, search button and search sheet, job page, match card,
  document panel), `journey` (setup bar, empty Discover states, job steps), `onboarding` (six-step wizard), `tour` (first-visit tour of the demo: an intro and a spotlight that moves through nine stops, from the deck to the résumé step and "Fill the gaps"; remembered in the browser's local storage, restarted from the demo banner), `profile` (view, structured/JSON editor, review, missing-info answers),
  `applications` (kanban with drag and drop plus a per-card status menu), `settings` (search preferences form, deck settings: swipe mapping, threshold, toggles, glass level).
- `src/components/`: design primitives (`ui.tsx`: `Button`, flat `Card`, `Dot`/`Meta`, fields, `SegmentedControl`),
  native `<dialog>` that becomes a bottom sheet on phones, toast stack. Look and fonts:
  [ADR-012](adr/ADR-012-neon-glass-design-language.md); phone and desktop rules (top navigation from 1024 px, one
  bottom dock below that, publishing its height as `--dock-h`): [ADR-011](adr/ADR-011-design-language-and-fonts.md);
  swipe deck: [ADR-013](adr/ADR-013-triage-and-swipe-deck.md). Pages pick their own width; `AppShell` sets the margins.
- Routing: `/` redirects to `/app/`; `/app/*` has a history fallback (`app/route_groups/spa.py`); secondary pages are lazy-loaded chunks. `/case-study` serves only the plain files in `app/case_study/` (one page, its stylesheet, fonts and images; same strict policy, so no inline styles or scripts). Flask serves no `/static` (the app is created with `static_folder=None`).
- Tests: Vitest + Testing Library + MSW (`src/test/`); `npm run check` = types current, typecheck, lint, format,
  tests, build. Browser tests in `web/e2e/` (Playwright + axe) drive the built app against
  `scripts/e2e_web_server.py` (mock providers, temporary database) at phone, tablet and desktop sizes, in light and
  dark mode; which spec runs where is in `web/playwright.config.ts`. `src/lib/breakpoints.ts` holds the breakpoints.

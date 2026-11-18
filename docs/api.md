# HTTP API

Current behavior of every route. The machine-readable route list is [route-inventory.json](route-inventory.json)
(every method/path pair, excluding automatic HEAD/OPTIONS); a test fails if it drifts from the registered routes —
regenerate with `python scripts/export_route_inventory.py`. The `/api/v1` contract is [openapi.json](openapi.json).
Error codes: [error-codes.md](error-codes.md).

**One API:** everything the web app does goes through `/api/v1/*`; slow work (search, scoring, writing, profile
building) starts a task that you poll at `GET /api/v1/tasks/{id}`. The Jinja UI, its `/ui/*` form routes and the older
unversioned JSON routes (`/auth/*`, `/profile/*`, `/tasks*`, `/resume/*`, `/jobs/*`, `/applications*`, `/run/daily`,
`/status`) were removed in Phase 5.

## Conventions

### Auth and permissions

- Auth is a Flask session cookie; browsers use same-origin requests.
- Every `POST/PUT/PATCH/DELETE` except sign-in, sign-up and sign-out requires a real login. The `demo` user is
  never signed in: visiting a page creates no session, and under `DEMO_MODE` every write is refused (403 / 1004).
- `/api/v1/*` (except session and config) requires a login and always returns the caller's own data, admins
  included. Unauthenticated → 401. Resources that exist but belong to someone else return 404.
- Profiles always belong to the current user.

### Request rules

- JSON bodies must be objects; malformed JSON, arrays, numbers or `null` → 400. Write requests with a body must be
  JSON (415 otherwise); attachments travel as base64 inside the JSON.
- Writes are rejected (403) when `Origin`/`Referer` is cross-site or `Sec-Fetch-Site: cross-site`. CLI
  clients without these headers are allowed. This is not a CSRF-token protocol; a cross-origin deployment
  needs its own auth/CORS/CSRF design.
- Size limits: 42 MiB per request; attachments 10 MiB each, 30 MiB total decoded. Size is computed from
  the decoded bytes; a client-supplied `size` is ignored.
- Responses default to `Cache-Control: no-store`; fingerprinted web-app assets are immutable.

### Correlation IDs ([ADR-003](adr/ADR-003-request-correlation-id.md))

- Every response carries `X-Correlation-ID`. A client-supplied value is reused if it is 1–64 chars of
  `A-Z a-z 0-9 _ - .`; otherwise a new one is generated. Task reads return the task's original ID.
- Envelopes include `correlation_id`; tasks store it.
- Never put PII, tokens or secrets in a correlation ID. Request/task logs should include
  `correlation_id`, path, user/subject, `task_id` and state.

### Response shapes

Every `/api/v1/*` response uses an envelope:

```json
{"status": "ok", "correlation_id": "req_...", "data": {}}
{"status": "error", "error_code": 2001, "message": "invalid payload", "correlation_id": "req_..."}
```

Errors always use the envelope, with optional `details: [{field, message}]` for validation errors; unknown routes,
wrong methods and unhandled exceptions included (500 → code 5001, no internal detail). Boundary errors from
`app/guards.py` also carry a legacy `error` field with the same text.

| HTTP | Meaning | Client handling |
|---|---|---|
| 400 | Invalid field/format | Show field hint; fix and retry |
| 401 | Not logged in / no real write identity | Show login |
| 403 | Cross-site write, registration closed, or read-only demo (1004) | Don't retry |
| 404 | Missing or not visible | Clear selection; reload list |
| 409 | Profile not approved, report/profile version mismatch, match not viewed, no decision, task has no successful result | Route the user to re-evaluate / review / decide |
| 413 | Body or attachment too large | Shrink attachments |
| 415 | Unsupported Content-Type | Fix request format |
| 429 | Active task capacity reached | Let the user retry after tasks finish |
| 5xx | Server/provider failure | Keep the correlation ID; never auto-retry writes |

## Workspace API (`/api/v1`)

| Method & path | Purpose | Params | `data` |
|---|---|---|---|
| `GET /api/v1/overview` | Personal summary, profile gate, today's quota | — | `counts {jobs, evaluated, applications}`, `readiness`, `usage[]` |
| `GET /api/v1/search-suggestions` | Search changes suggested by the reasons given for skips (three or more of one reason); never applied automatically | — | list of `{kind: remove_level\|exclude_word, value, count}` |
| `GET /api/v1/journey` | Where the user is in setup: six steps (`profile`, `search_prefs`, `find_jobs`, `pick`, `write`, `apply`), each `done\|current\|todo` with a `reason_code` and a call to action; counts; `discover` says why the Discover deck is empty ([ADR-015](adr/ADR-015-guided-journey.md)) | — | `completed, skipped, current, steps[], counts, discover` |
| `PUT /api/v1/journey` | Hide (`true`) or show the setup guide | `{skipped}` | journey |
| `GET /api/v1/session` | Who is signed in (no login needed) | — | `{user: {id, username, is_admin} \| null}` |
| `POST /api/v1/session` | Sign in; 401 / code 1001, or 429 / code 1005 after 10 failures in 15 min | `{username, password}` | session |
| `DELETE /api/v1/session` | Sign out | — | `{user: null}` |
| `POST /api/v1/account` | Create an account and sign in; 403 / code 1003 unless `REGISTRATION_MODE=open`, 409 / code 3004 if the username is taken or reserved | `{username (3–32 of a-zA-Z0-9_.-), password (≥ 8)}` | session (201) |
| `GET /api/v1/config` | Public client configuration (no login needed) | — | `registration_open, demo_mode, demo_live, guest, llm_provider (gemini\|mock), job_source, search_results_per_run` (the real per-run cap, `pipeline.daily_limit`) |
| `GET /api/v1/demo/sample-resumes/{kind}` | Demo only: the fictional sample résumé as `text`, `pdf`, `docx` or `image` (404 outside the demo) | — | the file |
| `POST /api/v1/demo/guest` | Live demo only ([ADR-018](adr/ADR-018-live-demo-guest-workspaces.md)): start a guest workspace with the sample profile and sign in to it; 403 / 1004 when the live demo is off, 429 / 3005 when today's guest limit (in total, or for the caller's address) is reached | — | `user` (201) |
| `GET /api/v1/profile` | Full Master Profile for review/edit screens | — | `profile` (null if none), `readiness` |
| `GET /api/v1/profile/versions` | All profile versions, newest first (no JSON) | — | list |
| `POST /api/v1/profile/{id}/review` | Approve or mark `needs_changes` | `{review_status, review_note?}` | profile |
| `PATCH /api/v1/profile` | Save the owner's own edit as a new version, approved (`model_name: user_edit`) | `{master_profile}` | profile (201) |
| `POST /api/v1/profile/synthesize` | Build a new version from text, details and base64 files (PDF, PNG, JPEG, WebP, or Word `.docx`, read as text) → `synthesize_profile` task. A live-demo guest must send `sample` (`text \| pdf \| docx \| image`) and builds from the sample résumé; `sample` is 400 / 2002 for real accounts. File bytes are removed from the task record when it finishes | `{resume_text?, extra_context?, links?, user_details?, attachments?[{name, mime_type, data_base64}]}` | task (202) |
| `POST /api/v1/profile/supplement` | Answer missing-information questions → `supplement_profile` task | `{profile_id?, selected_fields, answers, additional_context?}` | task (202) |
| `GET /api/v1/jobs` | Paged own jobs | `limit` 1–100 (20), `offset`, `status`, `min_score`, `q` (title/company), `include_archived` (false), `triage` `pending\|skipped\|waitlisted\|accepted` (`pending` = no swipe decision yet, the Discover deck), `scored` `true\|false` (`false` = no match score yet), `sort` `newest\|score` | `items, total, limit, offset` |
| `GET /api/v1/jobs/{id}` | Job detail | — | job fields + `description`, `match` (report or null), `match_uses_latest_profile`, `decision`, `documents {resume, cover_letter}` (latest version meta), `description_is_snippet`, `application_updated_at` |
| `PUT /api/v1/jobs/{id}/description` | Replace the job's text with the whole posting (200–20000 characters; own jobs only), then call `evaluations/rerun` with `job_ids: [id]` to score it again | `{description}` | job detail |
| `PUT /api/v1/jobs/{id}/triage` | Swipe decision. `skipped` / `waitlisted` only record it; `accepted` also records the generation decision and starts the document task(s). 409 (3004) when the job is not evaluated yet. At the per-user task limit the decision stays stored and `queued_for_later` is true (no 429); the client starts the rest when slots free (`GET /jobs?triage=accepted` lists them with `has_resume`, `has_cover_letter`, `triage_generate`) | `{action: skipped\|waitlisted\|accepted, generate?: resume\|resume_and_cover_letter, reason?: too_senior\|too_junior\|wrong_field\|location\|pay\|other}` (`reason` only for skips) | `job_id, action, generate, tasks[], queued_for_later` |
| `DELETE /api/v1/jobs/{id}/triage` | Undo a swipe; cancels queued generation tasks of that job | — | job detail |
| `POST` / `DELETE /api/v1/jobs/{id}/archive` | Hide / show a job in the default list | — | job detail |
| `POST /api/v1/searches` | Search the job board with saved preferences → `manual_search` task. One search per user at a time (another one with different options: 409 / 3004 "a job search is already running"; the identical request returns the running task) | `{force_when_high_missing?, fetch_limit?, score_limit?}`: `fetch_limit` 1–500 (null or above the cap = the cap), counted in new jobs only; `score_limit` 0–500 (null = score every new job, 0 = fetch only, N = score the first N) | task (202) |
| `POST /api/v1/jobs/manual` | Add a pasted job description and evaluate it → `manual_jd_match` task | `{title, description, company?, location?, url?, salary_min?, salary_max?}` | task (202) |
| `POST /api/v1/evaluations/rerun` | Score or re-score own jobs with the latest profile → `re_evaluate` task. `scope: "unscored"` takes own, non-archived jobs that have no score yet (newest first, up to `limit`); `job_ids` also accepts jobs without a score (their first score is created) | `{scope?, days?, limit?, job_ids?, force_when_high_missing?}` | task (202) |
| `GET /api/v1/tasks` | Task history; `active=true` returns only queued/running tasks (resume progress after a reload) | paging, `active` | `items, total, limit, offset`, newest first |
| `GET /api/v1/tasks/{task_id}` | Task state and progress — poll this while a task runs; `job_id` names the job for document generation (else null) | — | task |
| `POST /api/v1/tasks/{task_id}/cancel` | Cancel queued / request stop of running | — | task |
| `GET /api/v1/tasks/{task_id}/result` | Result of a succeeded task (409 otherwise) | — | result object |
| `POST /api/v1/jobs/{id}/documents` | Record "viewed + decided" and generate → `generate_resume` / `generate_cover_letter` task. 409 if the job has no evaluation | `{kind: resume\|cover_letter, style?, tone?}` | task (202) |
| `GET /api/v1/jobs/{id}/documents` | All versions of both documents, newest first | — | `{resume: [...], cover_letter: [...]}` (no content) |
| `GET /api/v1/documents/{kind}/{id}` | One version with Markdown and evidence map (`evidence_map.warnings`: problems the app found in the text; `retried: true` when the first draft was rejected and rewritten once; `claims[{text, status: supported\|inferred\|unsupported, profile_path, quote}]` and `audit {status: ok\|skipped, model_name, rewritten, unsupported}` from the fact check, [ADR-016](adr/ADR-016-grounded-documents.md); `model_name`, `prompt_version`) | — | document |
| `PUT /api/v1/documents/{kind}/{id}` | Save an edited copy as a **new** version (`origin: edited`); the original is kept | `{content_md}` | document (201) |
| `GET /api/v1/documents/{kind}/{id}/export` | Download as `format=pdf` (default) or `docx`; ATS-friendly single-column layout, filename `Company-Title-resume-v2.pdf` | `format` | file |
| `GET /api/v1/applications` | Every non-archived job with its application status and `follow_up_at`, for the kanban | — | list of cards |
| `PATCH /api/v1/jobs/{id}/application` | Update status and/or note | `{status?, note?}` | application state |
| `GET /api/v1/preferences` | Swipe mapping, deck filter and look settings (defaults merged in) | — | `swipe {left,right,up,down}`, `deck {min_score, mouse_drag, buttons}`, `ui {glass}` |
| `PUT /api/v1/preferences` | Replace them. Swipe actions: `skip`, `generate_resume`, `generate_resume_and_cover_letter`, `waitlist`, `details`, `none`; each used at most once. Unknown keys and out-of-range values are 400 | the same object | saved preferences |
| `GET /api/v1/search-preferences` | Effective search config | — | `config {adzuna: {...}, target_levels}`, `source: user\|default` |
| `GET /api/v1/search-preferences/suggested` | Settings prefilled from the latest profile (target roles → keywords, first preferred location, `sort_by: relevance`, `target_levels` from years of experience: one level either side, internships not counted); not saved | — | `config`, `source: suggested` |
| `PUT /api/v1/search-preferences` | Replace own search config | `{adzuna: {...}, target_levels?}` | saved `config`, `source: user` |

The machine-readable contract is [openapi.json](openapi.json), also served live at `GET /api/v1/openapi.json`
(OpenAPI 3.1, generated from the pydantic models in
`app/api_models.py` by `scripts/export_openapi.py`; CI fails on drift). Response schemas list every field as required (responses
always include all fields); a request model whose schema differs from the response model of the same name is published as
`<Model>Input` (e.g. `AdzunaSearchParamsInput`). The web app generates its TypeScript types from this file. `tests/integration/test_api_fuzz.py` fuzzes every operation from that document with schemathesis
(no 500s, documented statuses, responses matching their schemas). Request bodies and query strings are validated:
invalid values return 400 with code 2002 and per-field `details`. Responses are validated against their declared model.
Lists are ordered by id descending; offset pages can shift when new rows arrive, so refresh the first page.

- `profile` fields: `id, profile_version, model_name, created_at, review_status, review_note, reviewed_at_utc, master_profile`.
  No raw uploads, base64 or server paths. `master_profile` contains identity/contact, profile_summary,
  career_highlights, core_skills, skill_matrix, experiences, projects, education, certifications, languages,
  preferences, missing_information, field_confidence, completeness_score (+ `completeness_score_source`).
  Completeness is recomputed by the app on read (see [architecture.md#gates-and-invariants](architecture.md#gates-and-invariants)).
- Job items: `id, title, company, location, source, url, posted_date, created_at, salary_min, salary_max,
  match_score, years_asked_min, years_asked_max, recommendation_level, confidence, source_profile_id,
  source_profile_version, application_status, application_note`. The full match report and documents come from the job detail.
  `years_asked_min` / `years_asked_max` are the years of experience the posting text asks for ("5+ years" → 5 / null,
  "3 to 5 years" → 3 / 5; the highest stated minimum when it lists several; both null when it states none). They are
  read from the stored description on every read (`core/posting_years.py`, fixed rules, no AI), so a pasted full
  posting updates them, and they never change the match score. List items and the job detail both carry them.
- Search config (`JobSearchConfig`): `country` 2-letter lowercase; `keywords` non-empty array; `location`;
  `days_old` 1–365; `sort_by` `date|salary|relevance`; optional non-negative `salary_min/salary_max/distance`;
  `company, category, what_and, what_or, what_phrase, what_exclude`; optional booleans
  `full_time, part_time, permanent, contract`. `salary_max ≥ salary_min`; a contradictory employment-type pair resets to Any.
  Results are fixed to 10 × 1 page. PUT has **replace** semantics: omitted fields reset to defaults.
- `target_levels` (top level of the config): any of `junior, mid, senior, staff_plus, management`; empty means all levels. Postings whose title names a level that is not selected are dropped before they are stored or scored (`core/seniority.py`); a title with no level word counts as `mid`. The search task result reports `skipped_by_level`.
- `work_modes` (`remote, hybrid, onsite`; empty = any), `exclude_title_words` (whole words in the title, ≤ 20) and `knockouts` (`security_clearance, citizenship_required, no_sponsorship`) are the other top-level filters, applied with `adzuna.salary_min` (a posting whose stated maximum is lower is dropped) before a posting is stored ([ADR-017](adr/ADR-017-search-funnel.md)). The result reports `skipped_by_filters {salary, title_word, work_mode, knockout}`. Jobs from a search carry `relevance` (0–100, no AI call); a limited search (`score_limit`) scores the most relevant first.

```bash
curl -b cookies.txt http://127.0.0.1:5001/api/v1/jobs?limit=20
curl -b cookies.txt -X PUT -H 'Content-Type: application/json' http://127.0.0.1:5001/api/v1/search-preferences \
  -d '{"adzuna": {"country": "ca", "keywords": ["backend engineer"], "location": "Toronto"}}'
```

## Rules

- Every synthesis/supplement creates a new **pending** profile version; approving an older version does not open the
  search gate while a newer pending one exists. `force_when_high_missing` only applies to an **approved** profile with
  missing core fields (`identity.name`, `core_skills`, an empty `experiences` list); it never skips approval. Pasting a job (`POST /api/v1/jobs/manual`) only needs an approved profile with a name, 3+ skills and one experience. Search and re-evaluation tasks fail with a readable message until the
  latest version is approved and complete enough.
- Adzuna's search API returns only a 500-character preview. The full posting is read from the job board's detail page during the search and again before any scoring ([ADR-019](adr/ADR-019-full-job-descriptions.md)); a job whose full text could not be read keeps `description_is_snippet: true`, is never scored, and is scored once the posting is pasted (`PUT /api/v1/jobs/{id}/description`).
- `match` (job detail) fields: `total_score, dimension_scores, match_reasons, strengths, gaps, risk_flags,
  recommendation_level, confidence, missing_information, fit_reason, source_profile_id, source_profile_version`.
- Generation: `POST /api/v1/jobs/{id}/documents` is the user's explicit "I viewed the match and want this document"
  decision; it records that and starts the task. The task uses the job owner's latest approved profile; if that
  differs from the one the match was made from in a way the scorer can see (skills, experience, level, preferences; not a corrected name or phone number) it fails ("different profile version", re-evaluate first), and `match_uses_latest_profile` is false. Each new
  evaluation clears the viewed flag and decisions. Regenerating a cover letter only moves `draft → ready`; later
  progress and notes are kept. Documents live only in the database; download them with
  `GET /api/v1/documents/{kind}/{id}/export`.

## Async tasks

Contract: [ADR-002](adr/ADR-002-async-task-contract.md). Tasks are started by the endpoints marked "task" above (they
answer 202 with the task) and followed through `GET /api/v1/tasks/{task_id}` (state, progress, `error_message_safe`),
`GET /api/v1/tasks/{task_id}/result` (409 unless succeeded) and `POST /api/v1/tasks/{task_id}/cancel` (cooperative:
queued → cancelled immediately, running stops at the next stage boundary, idempotent). Progress events are stored in
`task_events` for diagnostics; there is no event or SSE endpoint.

Task types and payloads:

- `generate_resume` — `job_id` (positive int), `profile_id?, style?, decided_by?`; submitted by `POST /api/v1/jobs/{id}/documents`
- `generate_cover_letter` — `job_id`, `profile_id?, tone?`; same endpoint
- `manual_search` — `force_when_high_missing?, fetch_limit?, score_limit?`; uses the caller's saved search config (`POST /api/v1/searches`). Result: `inserted_count, evaluated_count, skipped_by_level, skipped_by_filters, duplicates_skipped, fetch_limit` (used), `score_limit, not_scored_count` (= `not_scored_by_choice` + `not_scored_by_quota` + `not_scored_no_description` + failed), `quota_exhausted, failed_job_ids, source_stats[]`. When the daily AI quota runs out scoring stops at once; the task still succeeds and the unscored jobs stay saved.
- `manual_jd_match` — `title, description`; optional `company, location, url, salary_min, salary_max` (`POST /api/v1/jobs/manual`)
- `re_evaluate` — `scope` (default `all`), `days` 1–365 (default 30), `limit` 1–500 (default 100), `job_ids[]` ≤ 500, `decided_by?, force_when_high_missing?` (`POST /api/v1/evaluations/rerun`); `scope` is `all`, `recent_days`, `low_confidence`, `high_risk` or `unscored`. Result adds `quota_exhausted`, `not_attempted_count` and `needs_description_count` (jobs left unscored because their full text could not be read): scoring stops at the first exhausted daily quota and the task still succeeds
- `synthesize_profile` — `input_bundle`, `attachments[]` (≤ 10); submitted by `POST /api/v1/profile/synthesize`; attachment bytes are removed from the stored payload when the task ends
- `supplement_profile` — `profile_id?, selected_fields[], answers{}, additional_context?`; submitted by `POST /api/v1/profile/supplement`

States: `queued, running, succeeded, failed, cancelled, expired`. Implemented transitions:
`queued→running` (claimed once), `queued|running→succeeded|failed|cancelled`, `queued→expired`. Every transition is a
guarded update (`WHERE state IN (...)`), so a task reaches exactly one terminal state even when a cancel races a completion.

Behavior:

- Request bodies are validated before a task is created; invalid → 400, no placeholder task.
- Capacity: max 100 active tasks globally and 3 per user (persisted check) → 429 / code 3005.
- Duplicates: submitting exactly the same request (same type and payload) while the first is still queued or running returns that task again (202) instead of starting a second one, so a double click or a retry costs nothing.
  Each process runs at most 2 tasks at once.
- Cancellation cannot undo provider calls, cost, or committed data. If the result was committed before
  the cancel, the task stays `succeeded` with `cancel_requested=true` and the result remains readable.
- Orphans: a queued task that no runner started within 60 s is picked up by any live runner (one wins the claim), so a restart does not leave work waiting for the 30-minute expiry.
- Recovery: running tasks refresh `heartbeat_at_utc` every 30 s. At startup and every 30 s, a running task without a
  heartbeat for 5 minutes becomes `failed` ("interrupted … please try again") and a queued task not started within
  30 minutes becomes `expired`, so orphaned tasks stop counting toward capacity. Multiple worker processes are safe
  because only stale heartbeats are recovered.
- `error_message_safe` is always safe to display: expected failures (`core/errors.py:UserFacingError`, provider and
  gate errors) keep their message; anything else shows "Something went wrong (ref <correlation_id>)" and is logged
  server-side with its traceback.
- Clients must not auto-retry writes: a timeout does not mean the work didn't happen. Check task history first.

## System routes

| Method & path | Purpose |
|---|---|
| `GET /health`, `GET /healthz` | Liveness only (`status: ok`); used by Docker health checks |
| `GET /readyz` | Readiness: 200 when the database answers and all migrations are applied, else 503 with the reason |
| `GET /` | Redirects to the web app at `/app/` (served by `app/route_groups/spa.py` with a client-routing fallback) |

## Compatibility rules

1. A UI may change layout, navigation and framework freely, but must keep domain state and the `/api/v1` contract.
2. After adding/removing routes run `python scripts/export_route_inventory.py`, `python scripts/export_openapi.py` and
   `(cd web && npm run gen:api)`, and update this file.
3. The route inventory is coverage only, not a schema; `openapi.json` describes `/api/v1`.

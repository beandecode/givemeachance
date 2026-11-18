# Contributing — start here

Single entry point for anyone working on this repo.
Start here, then read the files the routing table below lists for your task.

GivemeaChance is a Flask + SQLite job-search assistant: build a reviewed Master Profile,
find or paste jobs, get an explainable AI match, generate a tailored resume / cover letter,
and track applications. Current improvement work follows [docs/roadmap.md](docs/roadmap.md).

## Routing table — what to read for each task

| Task | Read (docs) | Code entry points |
|---|---|---|
| First time here / big picture | [README.md](README.md), [docs/architecture.md](docs/architecture.md) | `app/__init__.py`, `app/routes.py` |
| Add or change an HTTP endpoint | [docs/api.md](docs/api.md), [docs/error-codes.md](docs/error-codes.md) | `app/api.py` (`api_route`), `app/api_models.py`, `app/route_groups/` (routes must live here — the route inventory only scans this folder), `core/*_service.py`; then `python scripts/export_route_inventory.py`, `python scripts/export_openapi.py` and `(cd web && npm run gen:api)` |
| Database schema / queries / migrations | [docs/architecture.md#data](docs/architecture.md#data) | `core/db/migrations.py` (append a migration), `core/repositories/`, `core/persistence.py` |
| LLM prompts, evaluation, document generation, model choice | [docs/architecture.md#llm-and-providers](docs/architecture.md#llm-and-providers), [ADR-016](docs/adr/ADR-016-grounded-documents.md) (fact check) | `core/llm_prompts.py`, `adapters/llm/` (`get_llm`), `core/evaluate.py`, `core/generation_service.py`, `llm.model` in `config/settings*.yaml` |
| Master Profile synthesis / readiness gates | [docs/architecture.md#gates-and-invariants](docs/architecture.md#gates-and-invariants) | `core/profile_synthesis.py`, `core/profile_readiness.py`, `core/profile_quality.py` |
| Job ingestion / search providers | [docs/architecture.md#llm-and-providers](docs/architecture.md#llm-and-providers) | `core/ingest.py`, `adapters/jobs/`, `core/job_fulltext.py`, `core/search_preferences.py`, `core/triage_service.py`, [ADR-019](docs/adr/ADR-019-full-job-descriptions.md) (full descriptions, never score a preview), [ADR-014](docs/adr/ADR-014-user-controlled-search-and-scoring.md) (search and scoring options), [ADR-017](docs/adr/ADR-017-search-funnel.md) (filters, relevance, skip reasons), [ADR-013](docs/adr/ADR-013-triage-and-swipe-deck.md) (swipe decisions) |
| Async tasks (queue, progress, cancel) | [docs/api.md#async-tasks](docs/api.md#async-tasks), [ADR-002](docs/adr/ADR-002-async-task-contract.md) | `core/async_tasks.py`, `core/task_service.py` (`submit_task`), `core/task_handlers.py`, `core/profile_tasks.py`, `core/task_contracts.py` |
| PDF / DOCX export | [docs/architecture.md#main-flows](docs/architecture.md#main-flows), [ADR-007](docs/adr/ADR-007-pure-python-export.md) | `core/export/` (`blocks.py` → `pdf.py` / `docx.py`), `app/route_groups/api_documents.py` |
| Guided flow (setup steps, empty states, job steps, follow-ups) | [ADR-015](docs/adr/ADR-015-guided-journey.md), [docs/api.md](docs/api.md) | `core/journey_service.py`, `web/src/features/journey/`, `web/src/features/onboarding/` |
| Frontend (React app at `/app`), look and feel | [docs/architecture.md#web-app](docs/architecture.md#web-app), [ADR-008](docs/adr/ADR-008-react-spa.md), [ADR-012](docs/adr/ADR-012-neon-glass-design-language.md) (look, fonts, glass), [ADR-011](docs/adr/ADR-011-design-language-and-fonts.md) (phone and desktop rules) | `web/src/features/`, `web/src/api/` (types generated from `docs/openapi.json`), `app/route_groups/spa.py` |
| Docker, demo container, hosting | [docs/operations.md#docker](docs/operations.md#docker) | `Dockerfile`, `docker-compose.demo.yml`, `gunicorn.conf.py` |
| Public demo: read-only sample workspace, live guest workspaces, first-visit tour | [docs/operations.md#demo-read-only-no-keys](docs/operations.md#demo-read-only-no-keys), [ADR-009](docs/adr/ADR-009-read-only-demo-mode.md), [ADR-018](docs/adr/ADR-018-live-demo-guest-workspaces.md) (live demo, guests) | `core/demo.py`, `core/guest_service.py`, `app/guards.py`, `scripts/seed_demo.py`, `scripts/make_sample_resumes.py` (sample résumé in every format), `config/settings.demo*.yaml`, `docker-compose.demo.yml`, `web/src/features/tour/` |
| Measure match quality (labelled set, model comparison) | [docs/operations.md#measuring-match-quality](docs/operations.md#measuring-match-quality), [ADR-019](docs/adr/ADR-019-full-job-descriptions.md) | `scripts/labelling.py` (data stays in gitignored `output_localtest/labelling/`) |
| What to work on next / status | [docs/roadmap.md](docs/roadmap.md) | — |
| Why a design decision was made | `docs/adr/` — only the ADR for the decision you are changing | — |

**Generated or bulky files** (regenerate or skip them unless the task needs them): `docs/route-inventory.json` (generated; regenerate instead),
`docs/openapi.json` (generated), `web/src/api/schema.d.ts` (generated), `web/package-lock.json`, `app/spa_dist/` (build output),
`data/mock/*.json` (fixtures), `output*/`, `logs*/`.

## Commands

```bash
mise trust && mise install                    # Python + Node pinned in mise.toml; entering the folder activates .venv
./.venv/bin/pip install --require-hashes -r requirements-dev.txt   # runtime + dev tools (hash-locked)
export FLASK_SECRET_KEY="$(./.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
./.venv/bin/python run.py                     # http://127.0.0.1:5001 (providers per config/settings.yaml)
REGISTRATION_MODE=open SETTINGS_FILE=config/settings.test.yaml ./.venv/bin/python run.py   # mock providers, sign-up enabled
./.venv/bin/pytest -q                         # Python tests (mock providers, temp DBs; warnings are errors)
./.venv/bin/ruff check . && ./.venv/bin/ruff format --check . && ./.venv/bin/mypy   # lint, format, types
bash scripts/verify.sh                        # full gate: lint, types, tests, route/OpenAPI/doc checks, JS, web app, e2e
(cd web && npm ci)                            # web app dependencies (exact versions, no install scripts)
(cd web && npm run dev)                       # http://localhost:5173/app/ — proxies /api to Flask on :5001
(cd web && npm run check)                     # API types current, typecheck, lint, format, tests, build
(cd web && npx playwright install --only-shell chromium && npm run e2e)   # browser tests (Chromium kept in web/node_modules)
./.venv/bin/python scripts/export_route_inventory.py   # after adding/removing routes
```

## Conventions

- **Commits are authored by the maintainer (Bowen).** No co-author trailers in commit messages or PR descriptions.
- Work one roadmap phase at a time.
- **Keep the project isolated from the host and from other projects.** Language runtimes come from
  `mise.toml` (exact versions; never `brew install` a runtime or change the machine default). Dependencies stay
  inside the project (`.venv/`, `web/node_modules/`); never `pip install` outside `.venv`, `npm -g` or global
  pip/pipx. Services run in Docker Compose with explicit project names and `127.0.0.1` ports. Shared download caches
  (pip, npm, mise) are fine. Anything that cannot follow these rules: open an issue first.
- Run `bash scripts/verify.sh` before every commit and commit only if **its own exit status** is 0 (not a `| grep` of
  its output); CI runs the same checks on every push.
- Tests must use mock providers (`config/settings.test.yaml`) and temporary databases; never load
  `config/api-keys.env` or a personal `config/resume.yaml` in tests.
- Live-provider checks run in a separate container with its own data folder, never against a database you care about.
- Secrets live only in `config/api-keys.env` and `.env` (both gitignored). Never commit keys, passwords or session secrets.
- Dependencies: edit `requirements.in` / `requirements-dev.in`, then regenerate the locks with
  `pip-compile --generate-hashes --strip-extras --allow-unsafe <file>.in`; never hand-edit the `.txt` locks.
- mypy: modules listed under `[[tool.mypy.overrides]]` in `pyproject.toml` still have type errors; remove a module
  from that list when you refactor it. New modules must type-check.
- Never call a provider (LLM, job board) inside a write transaction — `release_write_lock` before, `begin_write` + re-check
  before saving results (docs/architecture.md#data). The test suite fails otherwise.
- SQL stays parameterized; every user-facing query goes through owner scoping (`core/persistence.py:job_visibility_clause`, `core/user_scope.py`).

## Keeping docs useful

- The doc set is fixed: `README.md` and `CONTRIBUTING.md` at the root, and `docs/{architecture,api,error-codes,operations,usage,roadmap}.md` + `docs/adr/`.
  Do not add new top-level Markdown files; extend the matching doc instead.
- A change that alters behavior updates the matching doc **in the same commit** (API → `docs/api.md`; deploy → `docs/operations.md`; …) and ticks its item in `docs/roadmap.md`.
- Record a new architectural decision as the next `docs/adr/ADR-NNN-*.md`; mark superseded ADRs instead of deleting them.
- Docs describe the current state. History belongs in git, not in dated "checkpoint" sections.
- `scripts/check_docs.py` (run by `verify.sh`) catches mechanical drift. **When a phase is complete**, also review
  the docs by hand against the phase's diff (`git diff <phase-start>..HEAD --stat`) before calling it done:
  every changed area's doc and routing-table row, the architecture code map, `docs/api.md` for new endpoints and
  task types, `docs/operations.md` for run/deploy changes, roadmap ticks, and a new ADR for any architectural choice.

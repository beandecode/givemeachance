# Operations

How to run, verify, measure and package the app.

## Secrets

| File (gitignored) | Contents | Template |
|---|---|---|
| `config/api-keys.env` | `GEMINI_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` (loaded by `core/config.py` and compose `env_file`) | `config/api-keys.env.example` |
| `.env` | `FLASK_SECRET_KEY` (≥32 random chars), `SESSION_COOKIE_SECURE`, `REGISTRATION_MODE`, `ADMIN_BOOTSTRAP_*`, `DEMO_FLASK_SECRET_KEY` (compose reads it automatically) | `.env.example` |

Other runtime settings: `REGISTRATION_MODE` (default `closed`; `open` enables self-service sign-up — accounts otherwise
come from `ADMIN_BOOTSTRAP_*`). `TRUSTED_PROXY_HOPS` (default `0`) — set to the number of reverse proxies in front of the
app (e.g. `1` behind one reverse proxy or tunnel) so client IP and scheme come from `X-Forwarded-*`; leave `0` when the port
is reachable directly, otherwise clients can spoof those headers.

Generate a session secret: `python -c 'import secrets; print(secrets.token_urlsafe(48))'`.
The app refuses to start with a missing or placeholder `FLASK_SECRET_KEY`.

## Local (no Docker)

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp config/api-keys.env.example config/api-keys.env    # fill keys for live mode
export FLASK_SECRET_KEY="$(./.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
./.venv/bin/python run.py                              # http://127.0.0.1:5001, debug off (FLASK_DEBUG=1 to enable)
```

Mock mode without keys: `REGISTRATION_MODE=open SETTINGS_FILE=config/settings.test.yaml ./.venv/bin/python run.py`.

Web app: `(cd web && npm ci && npm run build)` writes `app/spa_dist/`, which Flask serves at
`http://127.0.0.1:5001/app/`. For UI work run Flask as above plus `(cd web && npm run dev)` and open
`http://localhost:5173/app/` (hot reload; `/api` is proxied to `GMC_BACKEND`, default `http://127.0.0.1:5001`).
`/` redirects to `/app/`.

CLI: `./.venv/bin/python scripts/calibration_report.py <username>` (match scores per swipe/application outcome, read-only, to choose the Discover threshold).

## Verification

```bash
mise trust && mise install         # Python + Node pinned in mise.toml (creates .venv on first use)
./.venv/bin/pip install --require-hashes -r requirements-dev.txt   # dev tools (pytest, ruff, mypy, pip-tools)
./.venv/bin/pytest -q             # Python tests: temp DBs, mock providers, public resume example
./.venv/bin/ruff check . && ./.venv/bin/ruff format --check . && ./.venv/bin/mypy
(cd web && npm ci)                 # web app dependencies into web/node_modules
(cd web && npx playwright install --only-shell chromium)   # test browser, also inside web/node_modules
bash scripts/verify.sh             # + route inventory, OpenAPI and doc checks, web app check (types, lint, unit tests, build), browser tests
```

Toolchain: [mise](https://mise.jdx.dev) installs the exact Python and Node versions from `mise.toml` once
(shared with other projects that pin the same version; the machine default is untouched) and activates this
project's `.venv` when you enter the folder. CI uses the same file via `jdx/mise-action`, and the Docker base
image pins the same Python. `verify.sh` loads the mise environment itself. Override `PYTHON_BIN` / `NODE_BIN` if
needed. `scripts/check_docs.py` (part of `verify.sh`) fails on
doc drift: extra Markdown files, broken links or anchors, missing code paths, modules missing from the
architecture code map, undocumented task types. Tests never load personal credentials or write production artifacts.

## Measuring match quality

How well the score agrees with a person's judgment, on real postings (roadmap phase 11,
[ADR-019](adr/ADR-019-full-job-descriptions.md)). Everything lives in the gitignored `output_localtest/labelling/`:
the postings belong to their publishers, `resume.txt` is a résumé with names and contacts removed, and the labels are
the labeller's own. The commands that call a provider run where the keys are loaded: here, a container started from
the image with `config/api-keys.env` and live providers, shown as `<container>`.

```bash
docker exec -i <container> python - collect < scripts/labelling.py      # ~48 postings -> jobs.json
./.venv/bin/python scripts/labelling.py fulltext                                    # full text -> jobs-full.json
./.venv/bin/python scripts/labelling.py serve [--host <LAN address>]                # label at :5031, scores hidden
docker exec -i <container> python - score --model <id> --jobs jobs-full.json < scripts/labelling.py
```

`serve` has no sign-in: bind it to a LAN address only on a network you trust, and stop it when done. `score` builds a
profile from `resume.txt` once (`profile.json`) and scores every posting with the app's evaluator for one model into
`scores-<model>[-jobs-full].json`, counting its own calls and tokens instead of using the app quota; it can be
re-run after an interruption. `./.venv/bin/python scripts/labelling.py report [scores-<model>-jobs-full.json ...]`
compares the scores with `labels.json` on the host (no provider call): how often the score puts a pair in the labeller's
order, with 95% intervals from resampling (fixed seed), the fitting roles that reach the swipe deck, and the postings
that state the years asked. The level number is the seniority sub-score of "fits" against "too senior" roles; the
apply-above-skip number uses the total score.

The document fact check is measured the same way ([ADR-016](adr/ADR-016-grounded-documents.md#measured)), on 32
committed documents about the fictional demo candidate with planted false claims, in a blunt set (20, invented facts)
and a subtle set (12, real facts bent), one call per document and model:
`docker exec -i <container> python - run --model <id> [--set blunt|subtle|all] [--limit N] <
scripts/factcheck_eval.py` audits them into `output_localtest/factcheck/<model>.json` (resumable) and prints, per set,
the share of planted claims caught per type and the false-flag rate; `./.venv/bin/python scripts/factcheck_eval.py report` prints the table again on the host.

## Docker

The image is built in two stages: Node compiles the web app (`web/` → `app/spa_dist`), then the Python runtime image
copies the result; Node is not in the final image. It runs as the non-root user `app` (uid 10001); application code is
root-owned and read-only, only `output*/` and `logs*/` are writable. The base image is pinned by digest in the
`Dockerfile`. Gunicorn settings are in `gunicorn.conf.py` (`WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`;
access log to stdout). CI builds the image on every push.

### Demo (read-only, no keys)

```bash
docker compose -f docker-compose.demo.yml up --build     # http://127.0.0.1:5021/app/
docker compose -f docker-compose.demo.yml down
```

Needs no `config/api-keys.env` or `.env`. Every start seeds a fresh database (`scripts/seed_demo.py`: 8 sample jobs,
the complete profile of a fictional candidate from `data/mock/demo_profile.json`, résumés and cover letters for five of them, applications across the board) onto tmpfs and serves it
with `DEMO_MODE=true`: all writes — including sign-in and sign-up — return 403 / code 1004, and startup fails unless
providers are mock and `api_limits` are 0. Without Docker: `./.venv/bin/python scripts/seed_demo.py --force` then
`DEMO_MODE=true SETTINGS_FILE=config/settings.demo.yaml RESUME_FILE=config/resume.yaml.example ./.venv/bin/python run.py`.
`scripts/e2e_web_server.py --demo` serves the same thing for the browser tests. The profile carries two sample gap
questions so "Fill the gaps" shows, and the résumé step shows the sample résumé (`data/mock/sample_resume/`) in each
format; live guests can build a profile from it. After editing `casey-chen.txt`, run
`./.venv/bin/python scripts/make_sample_resumes.py` to render the PDF, Word and PNG again.

### Live demo (guest workspaces)

The public demo adds live guest workspaces on top of the read-only one
([ADR-018](adr/ADR-018-live-demo-guest-workspaces.md)). Run the same image with `DEMO_LIVE=true`, the settings file
`config/settings.demo-live.yaml` (real providers; 100 AI and 30 job-board calls a day for the whole demo, 25 and 3 per
guest), the provider keys from `config/api-keys.env` and a session key `DEMO_FLASK_SECRET_KEY`. Change the daily budget
in that settings file. The app itself caps new guests: `DEMO_GUESTS_PER_DAY` (default 40) in total and
`DEMO_GUESTS_PER_CLIENT` (default 5) per visitor address in 24 hours, which needs `TRUSTED_PROXY_HOPS` set to the
number of proxies in front of it. Keep the container off the host's ports and reach it only through the proxy.
`curl -s <demo address>/api/v1/config` then shows `"demo_mode": true, "demo_live": true`.

### Hosting the full app publicly

Keep the app behind a reverse proxy or tunnel with no host port published, set `SESSION_COOKIE_SECURE=true` and
`TRUSTED_PROXY_HOPS`, and keep registration closed. In front of it, either an identity check (recommended for a
showcase) or WAF rules, bot protection and rate limits, e.g. `POST /api/v1/session` 5/min per IP → challenge, then block
10 min; `POST /api/v1/account` 3/min → block 30 min; `POST /api/v1/searches` 2/min → block 15 min;
`/api/v1/profile/synthesize|supplement` 3/min and `/api/v1/jobs/*/documents` 4/min → challenge; 120/min per host →
challenge. The app itself locks a username for 15 minutes after 10 failed sign-ins; edge rate limits are still needed
against attempts spread over many usernames.

## Logs

`core/logging_setup.py` configures logging once per process (`create_app`, and gunicorn through `gunicorn.conf.py`).
`LOG_FORMAT=json` (the Docker image default) prints one JSON object per line on stderr: `ts, level, logger, msg`,
the request or task `correlation_id` and `task_id` when there is one, and for every call to an outside service one
line with `provider, op, attempt, latency_ms, status`. Locally the default is readable text; `LOG_LEVEL` sets the level.

Before a line leaves the process, API keys and tokens in query strings and headers (`app_key`, `key=`,
`x-goog-api-key`, bearer tokens), e-mail addresses and phone numbers are replaced with `***`. The same masking is
applied to error messages that are stored or shown (`failure_summary`, `user_message`). Follow a problem across the
app and the worker with its correlation ID:

```bash
docker logs <container> 2>&1 | grep req_0123abcd
```

`app.log_path` in the settings files is not used (everything goes to stderr).

## Database backups

The database runs in WAL mode, so a consistent copy needs the `-wal` file too — don't copy only the `.db` file of a
running app. Use SQLite's backup API instead, e.g.
`python -c "import sqlite3; sqlite3.connect('output/job_assistant.db').backup(sqlite3.connect('backup.db'))"`.
Before applying schema migrations, the app automatically writes `<db>.bak-<UTC timestamp>` next to the database;
delete old ones once the upgrade is confirmed.

## Time and persistence

Timestamps are stored as timezone-aware UTC ISO-8601 (no DST issues); convert to `America/Toronto` only
when displaying. Generated documents live only in the database (no file copies); download them as PDF/DOCX
through the export endpoint.

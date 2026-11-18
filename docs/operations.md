# Operations

How to run, deploy and verify the app. Guardrail: **only the localtest stack is used for live-provider
verification; the main stack, the public demo and Cloudflare (`docker-compose.app.yml`,
`docker-compose.demo-public.yml`, the tunnel) are not started, stopped or changed unless the maintainer explicitly asks.**

## Secrets

| File (gitignored) | Contents | Template |
|---|---|---|
| `config/api-keys.env` | `GEMINI_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` (loaded by `core/config.py` and compose `env_file`) | `config/api-keys.env.example` |
| `.env` | `FLASK_SECRET_KEY` (≥32 random chars), `SESSION_COOKIE_SECURE`, `CLOUDFLARE_TUNNEL_TOKEN`, `ADMIN_BOOTSTRAP_*` (compose reads it automatically) | `.env.example` |

Other runtime settings: `REGISTRATION_MODE` (default `closed`; `open` enables self-service sign-up — accounts otherwise
come from `ADMIN_BOOTSTRAP_*`). `TRUSTED_PROXY_HOPS` (default `0`) — set to the number of reverse proxies in front of the
app (e.g. `1` behind Cloudflare Tunnel) so client IP and scheme come from `X-Forwarded-*`; leave `0` when the port
is reachable directly, otherwise clients can spoof those headers.

Generate a session secret: `python -c 'import secrets; print(secrets.token_urlsafe(48))'`.
The app refuses to start with a missing or placeholder `FLASK_SECRET_KEY`. Rotate the tunnel token if it leaks.

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
the labeller's own. Keys are only loaded inside the localtest container, so the commands that call a provider run there.

```bash
docker exec -i openclaw-app-localtest python - collect < scripts/labelling.py      # ~48 postings -> jobs.json
./.venv/bin/python scripts/labelling.py fulltext                                    # full text -> jobs-full.json
./.venv/bin/python scripts/labelling.py serve [--host <LAN address>]                # label at :5031, scores hidden
docker exec -i openclaw-app-localtest python - score --model <id> --jobs jobs-full.json < scripts/labelling.py
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
`docker exec -i openclaw-app-localtest python - run --model <id> [--set blunt|subtle|all] [--limit N] <
scripts/factcheck_eval.py` audits them into `output_localtest/factcheck/<model>.json` (resumable) and prints, per set,
the share of planted claims caught per type and the false-flag rate; `./.venv/bin/python scripts/factcheck_eval.py report` prints the table again on the host.

## Docker stacks

The image is built in two stages: Node compiles the web app (`web/` → `app/spa_dist`), then the Python runtime image
copies the result; Node is not in the final image. Compose project names are explicit so stacks never collide.

| Stack | Files | Project | Port | Data | Purpose |
|---|---|---|---|---|---|
| Main | `docker-compose.app.yml` | `openclaw-main` | 127.0.0.1:5001 | `output/`, `logs/` | The full app with real providers (2 gunicorn workers). Its container is stopped while the public demo answers on the tunnel; its data stays in `output/` |
| Main + tunnel | `+ docker-compose.cloudflare.yml` | `openclaw-main` | none (internal only) | same | Public link via Cloudflare |
| Localtest | `docker-compose.localtest.yml` | `openclaw-localtest` | `${LOCALTEST_BIND_ADDR:-127.0.0.1}:5011` | `output_localtest/`, `logs_localtest/` | Live-provider staging (1 worker while on SQLite) |
| Demo | `docker-compose.demo.yml` | `gmc-demo` | 5021 | tmpfs (`output_demo/`, `logs_demo/`) | Read-only demo, no keys ([ADR-009](adr/ADR-009-read-only-demo-mode.md)) |
| Public demo | `+ docker-compose.demo-public.yml` | `gmc-demo` | none (tunnel) | same | What the public address serves: the demo plus live guest workspaces ([ADR-018](adr/ADR-018-live-demo-guest-workspaces.md)) |

### Localtest (staging with real providers)

```bash
bash scripts/restart_localtest.sh
```

The wrapper refuses non-localtest compose files, checks that `config/api-keys.env` has real keys and that
`config/settings.localtest.yaml` uses real providers, then runs `down → build → up` non-interactively
(no compose menu/TTY progress) and polls `http://<bind address>:5011/health`.

**Testing from a phone:** set `LOCALTEST_BIND_ADDR=<this Mac's LAN IP>` in the gitignored `.env` (never `0.0.0.0`), run the
restart script and open `http://<ip>:5011/app/` on a device on the same network. The IP can change with DHCP; reserve it
in the router or update `.env`. The app is then reachable by everyone on that network and uses live provider keys, so
remove the line (or leave it empty) and restart when you are done.

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

**On the public address (live demo).** `jobs.<your-domain>` is served by this demo, not by the main stack. The overlay
`docker-compose.demo-public.yml` does two things:

- It joins the demo container to the main stack's network under the name `app`, which is where the tunnel sends that
  hostname, so nothing changes in the Cloudflare dashboard. The main `openclaw-app` container must stay stopped while
  the overlay is up (two containers must not answer to `app`).
- It turns on the live demo ([ADR-018](adr/ADR-018-live-demo-guest-workspaces.md)): `DEMO_LIVE=true`, the settings
  file `config/settings.demo-live.yaml` (real providers; 100 AI and 30 job-board calls a day for the whole demo, 25 and
  3 per guest), the provider keys from `config/api-keys.env` and a session key `DEMO_FLASK_SECRET_KEY` from `.env`.
  Change the daily budget in `config/settings.demo-live.yaml`. The app itself caps new guests: `DEMO_GUESTS_PER_DAY`
  (default 40) in total and `DEMO_GUESTS_PER_CLIENT` (default 5) per visitor address in 24 hours, which needs
  `TRUSTED_PROXY_HOPS=1` behind the tunnel (set by the overlay).

```bash
docker stop openclaw-app                                  # only if it is running
docker compose -f docker-compose.demo.yml -f docker-compose.demo-public.yml up -d --build
curl -s https://jobs.<your-domain>/api/v1/config          # "demo_mode": true, "demo_live": true
```

After a code change, run the `up -d --build` line again (about half a minute of downtime while the sample data is
seeded; guest workspaces are lost, the day's quota count too). The `cloudflared` container and any other site behind the
tunnel are not touched by any of this. To go back to the read-only demo, start it without the overlay's `DEMO_LIVE`
(set it to `"false"`); the keys are then unused.

### Demo monitoring

`scripts/check_demo.sh` checks two things and changes nothing: the public address answers `/health`, and today's calls
(AI and job board, from the demo's own usage table, read inside the container) are below 90% of the demo's daily
limits in `config/settings.demo-live.yaml`. Every run appends a line to `logs/demo-check.log`; a problem also shows a
macOS notification, once per change of state, and exits 1. Override `DEMO_URL`, `DEMO_CONTAINER` and `WARN_AT` in the
environment (for example `DEMO_URL=https://jobs.invalid.example bash scripts/check_demo.sh` to see the alert).

To run it every 15 minutes on this Mac, put the repository path into the template and load it (a manual step):

```bash
sed "s|__PROJECT__|$PWD|g" scripts/com.givemeachance.demo-check.plist > ~/Library/LaunchAgents/com.givemeachance.demo-check.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.givemeachance.demo-check.plist
launchctl bootout "gui/$(id -u)/com.givemeachance.demo-check"     # to stop it
```

The Mac must be awake and Docker running; a sleeping Mac checks nothing.

### Main stack (only when explicitly requested)

```bash
docker compose -f docker-compose.app.yml up -d --build
curl http://127.0.0.1:5001/health
docker compose -f docker-compose.app.yml down
```

SQLite lives under the bind-mounted `output/`, so stop/start keeps data.

Image: runs as the non-root user `app` (uid 10001); application code is root-owned and read-only, only `output*/` and
`logs*/` are writable. Base image is pinned by digest in the `Dockerfile` — bump it deliberately. Gunicorn settings are
in `gunicorn.conf.py` (`WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`; access log to stdout); a compose
`command:` with flags overrides them (localtest uses 1 worker).

## Public link via Cloudflare Tunnel (only when explicitly requested)

Today the tunnel's `jobs.<your-domain>` hostname reaches the public demo ([above](#demo-read-only-no-keys)). The steps
below put the main stack behind the tunnel instead; doing that means stopping the demo overlay first (only one
container may answer to `app`).

Assets: `docker-compose.cloudflare.yml` (removes the host port, adds `cloudflared`),
`scripts/preflight_secure_link.sh`, `scripts/start_public_secure_link.sh`,
`scripts/restart_public_secure_link.sh` (non-interactive restart + health checks).

The connector image is pinned (`cloudflare/cloudflared:2026.10.3`); never use `latest`, which does not refresh an image
already pulled. Versions before 2026.10.2 still trust the compromised eMudhra (emSign) intermediates (Cloudflare notice,
October 2026). This one connector can also serve other sites on the same Docker network, so never `down` the stack just to upgrade it.
To upgrade: bump the tag, then
`docker compose -f docker-compose.app.yml -f docker-compose.cloudflare.yml pull cloudflared && docker compose -f docker-compose.app.yml -f docker-compose.cloudflare.yml up -d --no-deps cloudflared`
(about a second of downtime on both hostnames; the app and the network are untouched), and check
`docker exec openclaw-cloudflared cloudflared --version` and the `Registered tunnel connection` log lines. Both origins
are plain HTTP inside the Docker network, so no origin certificate is involved; never set `noTLSVerify`.

1. `cp .env.example .env`, fill `FLASK_SECRET_KEY` and `CLOUDFLARE_TUNNEL_TOKEN`; ensure `config/api-keys.env` exists.
2. One-time in Cloudflare Zero Trust: Networks → Tunnels → create tunnel (Docker connector, copy token);
   add public hostname `jobs.<your-domain>` → service `HTTP` → `http://app:5001`.
3. Choose an access mode:
   - **Access mode (recommended for a showcase):** Zero Trust → Access → Applications → self-hosted app for
     the hostname; allow only your identity provider users / a reviewer allowlist (email OTP or Google/GitHub;
     Access isn't meant for a shared username/password; machines use Service Tokens).
   - **Public mode:** no Access app. Then turn on WAF Managed Rules and Bot Fight Mode, and add rate limits, e.g.
     `POST /api/v1/session` 5/min/IP → challenge then block 10 min; `POST /api/v1/account` 3/min → block 30 min;
     `POST /api/v1/searches` 2/min → block 15 min; `/api/v1/profile/synthesize|supplement` 3/min,
     `/api/v1/jobs/*/documents` 4/min → challenge; host-wide 120/min → challenge. Optionally restrict countries / challenge high-risk ASNs.
4. `bash scripts/preflight_secure_link.sh`, then `bash scripts/start_public_secure_link.sh`.
5. Check: `docker compose -f docker-compose.app.yml -f docker-compose.cloudflare.yml ps` (app must **not**
   publish `0.0.0.0:5001`) and `... logs -f cloudflared` (look for `Registered tunnel connection`).
   Open the hostname; in Access mode a login challenge must appear first.
6. Stop: `docker compose -f docker-compose.app.yml -f docker-compose.cloudflare.yml down`.

Host checklist: the router does not forward 5001/80/443 to the machine; the local firewall is on; the app is
started with the tunnel overlay only when public exposure is intended.

Risk: Access mode + rate limits + strong app auth is acceptable for a demo; Public mode with weak auth
hygiene invites credential stuffing and scraping. The app itself locks a username for 15 minutes after 10 failed
sign-ins; edge rate limits are still needed against attempts spread over many usernames.

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
docker compose -f docker-compose.localtest.yml logs app_localtest | grep req_0123abcd
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

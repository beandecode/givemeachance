# ADR-009: Read-only demo mode (`DEMO_MODE`)

Date: 2026-10-24
Status: Accepted; extended by [ADR-018](ADR-018-live-demo-guest-workspaces.md) (guest workspaces on real providers when `DEMO_LIVE` is on)

## Context

The project doubles as a portfolio piece, so strangers should be able to try it without keys, accounts or cost.
A personal instance must never be exposed for that: it holds a real profile and live provider keys.

## Decision

- **A separate, secret-free instance** (`docker-compose.demo.yml`, `config/settings.demo.yaml`): mock providers,
  every `api_limits` value 0, a database seeded on each start by `scripts/seed_demo.py` and kept on tmpfs.
- **`DEMO_MODE=true` makes the app read-only.** The write guard in `app/guards.py` refuses every `POST/PUT/PATCH/DELETE`
  (sign-in and sign-up included) with 403 / code 1004 before any route runs, so the
  database cannot change at runtime and no provider is reachable from a request.
- **No sign-in.** In demo mode an anonymous request resolves to the seeded reserved `demo` user for reads
  (`resolve_request_user`, `api_route`); outside demo mode that user is still treated as signed out. The seed builds
  the workspace under a temporary owner through the real product flow, then renames the owner to `demo` and
  randomizes its password.
- **Fail closed at startup:** `core/demo.assert_demo_safe` refuses to start unless the LLM provider and job sources are
  mock and all quota limits are 0; `FLASK_SECRET_KEY` is optional because no session is ever created.
- `GET /api/v1/config` exposes `demo_mode`; the SPA shows a banner, hides sign-out and maps code 1004 to a friendly
  message.

## Consequences

- One chokepoint to reason about: new write routes are covered automatically (a test sweeps every write route in the
  URL map and compares table row counts before and after).
- GET handlers must stay free of writes; lazily created tables are built by the seed so the served database never
  changes.
- Reaching a "try it for real" experience (own résumé, real AI) needs a normal local run, not the demo.

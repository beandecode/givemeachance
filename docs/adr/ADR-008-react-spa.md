# ADR-008: React single-page app served by Flask at /app

Date: 2026-10-20
Status: Accepted

## Context

The Jinja UI was a 9-step linear wizard with full page reloads, three polling mechanisms and ~1000 lines of global
JavaScript. Job hunting is one-time setup plus a repeated per-job loop, and the project doubles as a portfolio piece.
Phase 2 delivered a typed `/api/v1` with a generated OpenAPI document, so a client can be built from the contract alone.

## Decision

- **Stack:** Vite + React + TypeScript (strict) in `web/`; TanStack Query for server state, React Router for routing,
  Tailwind with CSS-variable design tokens (light/dark via `prefers-color-scheme`). Small dependency set: no UI kit,
  no toast or Markdown-sanitizer library with runtime-injected styles.
- **Contract:** TypeScript types are generated from `docs/openapi.json` (`openapi-typescript`, committed as
  `web/src/api/schema.d.ts`; `npm run check` fails on drift) and used through `openapi-fetch`. Response models mark
  every field required; request models with different optionality are emitted as `<Model>Input`.
- **Same origin:** Flask serves the production build from `app/spa_dist` at `/app` with a client-routing fallback
  (`app/route_groups/spa.py`). In development the Vite server proxies `/api` to Flask, so the session cookie and the
  cross-origin write guard work unchanged; no CORS and no token auth.
- **Strict CSP** on SPA responses: everything `'self'`, no inline scripts or `<style>` elements. Fingerprinted assets
  are cached for a year; `index.html` is `no-store`.
- **Background work:** one task provider follows every task returned by a 202 (and resumes `GET /api/v1/tasks?active=true`
  after a reload), polls each task every 1.5 s, shows progress inline and in a header tray, toasts the outcome and
  invalidates the affected queries. No SSE in the SPA.
- **Information architecture:** onboarding (résumé → review profile → search preferences) derived from saved state;
  jobs list; one job page with match, documents (generate, versions, edit as a new version, PDF/DOCX), and
  application status; kanban; editable profile; settings.
- **Build:** a multi-stage Docker build compiles the app with Node in a throwaway stage; the runtime image has no Node.

## Consequences

1. Two toolchains (Python + Node, both pinned in `mise.toml`); `verify.sh` and CI run both.
2. The API contract is the boundary: backend changes regenerate `docs/openapi.json` and the TypeScript types in the
   same commit, and the type checker shows every affected screen.
3. `/` redirects to `/app/`; the legacy Jinja UI moved to `/legacy` for one release and was removed in Phase 5.

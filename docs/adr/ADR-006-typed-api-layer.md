# ADR-006: In-house typed API layer instead of flask-openapi3

Date: 2026-10-20
Status: Accepted

## Context

The React SPA (roadmap Phase 3) needs a machine-readable contract for `/api/v1` so TypeScript types can be
generated and drift is caught in CI. The roadmap proposed flask-openapi3. A spike showed that switching the app to
its `OpenAPI` class breaks the ~40 legacy routes that take Flask path arguments (`TypeError: missing argument`)
and mixes those legacy routes into the generated document. Rewriting the legacy routes is wasted work because
Phase 5 deletes them.

## Decision

Keep plain Flask and add a small layer in the repository:

- `app/api.py:api_route` registers an endpoint with pydantic models for query, body and response. It enforces login,
  validates input (400 / code 2002 with per-field `details`), validates the handler's result against the declared
  response model, and wraps it in the envelope. Errors under `/api/` always use the error envelope; unhandled
  exceptions become 500 / code 5001 with a correlation ID and no internal detail.
- `app/openapi.py` builds an OpenAPI 3.1 document from that registry with pydantic's JSON Schema;
  `scripts/export_openapi.py` writes `docs/openapi.json`, which CI checks for drift and validates.
- Legacy routes are untouched.

## Consequences

1. No new runtime dependency; the contract comes from the same models that validate requests and responses.
2. About 250 lines of framework code to maintain, and no bundled Swagger UI (the JSON file can be opened in any viewer).
3. If the API outgrows this (auth schemes, file uploads, streaming), revisit a framework once Phase 5 has removed
   the legacy routes.

# Error Codes

Codes returned in the `error_code` field of the error envelope (see [api.md](api.md#response-shapes)):

```json
{"status": "error", "error_code": 2001, "message": "invalid payload", "correlation_id": "req_..."}
```

## Ranges

| Range | Category |
|---|---|
| 1000–1999 | Auth and permission |
| 2000–2999 | Request validation |
| 3000–3999 | Domain / business rule |
| 4000–4999 | External provider |
| 5000–5999 | Runtime / internal |

## Catalog

"Used" means the code is emitted by the current code; the others are reserved.

| Code | Name | HTTP | Safe message | Used |
|---|---|---|---|---|
| 1001 | AUTH_REQUIRED | 401 | login required | yes |
| 1002 | AUTH_INVALID_SESSION | 401 | invalid session | — |
| 1003 | FORBIDDEN_RESOURCE | 403 | permission denied / cross-origin write rejected | yes |
| 1004 | DEMO_READ_ONLY | 403 | this is a read-only demo: changes are disabled / turned off in the live demo | yes |
| 1005 | LOGIN_LOCKED | 429 | too many failed sign-in attempts | yes |
| 2001 | INVALID_PAYLOAD | 400 | invalid payload | yes |
| 2002 | INVALID_FIELD | 400 | invalid request (per-field `details`) | yes |
| 2003 | MISSING_REQUIRED_FIELD | 400 | required field missing | yes |
| 2004 | UNSUPPORTED_MEDIA_TYPE | 415 | unsupported media type | yes |
| 2005 | METHOD_NOT_ALLOWED | 405 | method not allowed | yes |
| 2006 | PAYLOAD_TOO_LARGE | 413 | request too large | yes |
| 3001 | PROFILE_NOT_READY | 409 | profile is not ready | — |
| 3002 | DECISION_GATE_BLOCKED | 409 | generation decision is required | — |
| 3003 | RESOURCE_NOT_FOUND | 404 | resource not found | yes |
| 3004 | CONFLICT_STATE | 409 | state conflict (username taken, job not evaluated yet, a job search is already running) | yes |
| 3005 | TASK_CAPACITY_EXCEEDED | 429 | task queue is full / the live demo reached today's visitor limit | yes |
| 4001 | PROVIDER_RATE_LIMIT | 429 | provider rate limited | — |
| 4002 | PROVIDER_UNAVAILABLE | 503 | provider unavailable | — |
| 4003 | PROVIDER_TIMEOUT | 504 | provider timeout | — |
| 5001 | INTERNAL_ERROR | 500 | Something went wrong (ref …) | yes |
| 5002 | TASK_RUNTIME_ERROR | 500 | task execution failed | yes (task `error_code`) |
| 5003 | STORAGE_ERROR | 500 | storage operation failed | — |

Generic HTTP errors are mapped by status (`core/errors.py:HTTP_STATUS_CODES`). Under `/api/` every error —
including unknown routes and unhandled exceptions — uses the envelope. Legacy JSON endpoints outside `/api/v1` still
answer `{"error": ...}` without a code until they are removed (roadmap Phase 5).

## Rules

1. Messages must be safe to show in the UI — no stack traces, SQL/OS errors or raw provider payloads.
2. Every error response includes `correlation_id`.
3. Codes are append-only; never reuse or renumber.

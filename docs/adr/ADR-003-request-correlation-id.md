# ADR-003: Correlation ID As Required Trace Primitive

Date: 2026-04-17
Status: Accepted

## Context

Current sync flow logs are difficult to trace end-to-end across user request, pipeline stage, and future async events.

## Decision

Standardize on correlation_id for all new async endpoints and progressively backfill sync endpoints.

## Consequences

1. Better debugging and incident triage.
2. Better observability for retries, failures, and user reports.
3. Requires envelope consistency and strict safe logging practices.

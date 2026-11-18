# ADR-004: SQLite Then PostgreSQL Migration Sequence

Date: 2026-04-17
Status: Partially superseded by [ADR-005](ADR-005-product-fit-and-growth-triggers.md): safe migration requirements remain accepted; PostgreSQL activation is needs-driven, not an inevitable next phase.

## Context

The project currently runs on SQLite and lacks migration tooling. Distributed queue runtime on SQLite increases lock risk.

## Decision

Keep SQLite during early refactor and contract validation, then introduce migration tooling and activate PostgreSQL before distributed Celery runtime.

## Consequences

1. Lower immediate migration risk.
2. Requires explicit migration and rollback rehearsal.
3. Delays distributed runtime until data layer is production-ready.

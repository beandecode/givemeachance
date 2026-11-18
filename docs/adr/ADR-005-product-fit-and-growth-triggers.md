# ADR-005: Product Fit Before Infrastructure Migration

Date: 2026-09-16
Status: Accepted for the current single-host, small-group assumption; reassess when deployment requirements change.

## Context

Route extraction makes boundaries clearer but does not establish operational reliability. Isolated probes reproduce SQLite writer contention across a provider call and a claimed task left running after its process exits. Product gaps include editable verified facts, immutable evaluation provenance and usable document downloads.

## Decision

1. Retain Python/Flask as a modular monolith and the adapter boundaries. Do not introduce a framework rewrite or microservices without a demonstrated need.
2. Retain SQLite conditionally. First move external calls outside write transactions and implement snapshot checks and safe result persistence. Choose PostgreSQL when measured write contention or multi-host requirements warrant it, with migrations and restore rehearsal.
3. Treat LocalTaskRunner as a temporary execution mechanism. Durable task state alone is insufficient. Add lease/recovery, idempotency and failure handling; separate execution from web-process lifetime before long-running public operation.
4. Keep the existing task HTTP contract independent of execution technology. Celery/Redis is a candidate for distributed scheduling needs, not an automatic next phase.
5. Prioritize factual editing/provenance and actual DOCX/PDF delivery. Establish model-quality samples before changing model defaults.
6. Preserve the UI-neutral JSON/client boundary; choose replacement UI technology after its interaction requirements are defined.

## Supersession and consequences

This supersedes the unconditional “then Celery/Redis” sequence in ADR-002 and the inevitable PostgreSQL activation sequence in ADR-004. Their contract-stability and safe migration/rollback requirements remain valid. Distributed deployment must not share a SQLite file across hosts as a shortcut.

The working application remains simpler to operate, but known task recovery and transaction gaps remain explicit release constraints. No performance capacity or model quality claim is inferred from mock tests. Current work items and acceptance criteria derived from this decision are tracked in the [roadmap](../roadmap.md).

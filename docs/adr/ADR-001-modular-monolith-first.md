# ADR-001: Modular Monolith First

Date: 2026-04-17
Status: Accepted

## Context

The current codebase is a Flask monolith with synchronous flows. Immediate microservice decomposition would increase delivery and operational risk before async contracts and observability are stable.

## Decision

Adopt a modular monolith first. Extract route business logic into service and helper modules while keeping deployment topology unchanged.

## Consequences

1. Faster delivery with lower migration risk.
2. Clear internal boundaries for future extraction.
3. Requires discipline in module boundaries and API contracts.

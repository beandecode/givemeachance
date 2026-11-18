# ADR-002: Async Task Contract Before Runtime Swap

Date: 2026-04-17
Status: Partially superseded by [ADR-005](ADR-005-product-fit-and-growth-triggers.md): stable task contracts remain accepted; Celery/Redis is conditional, not an automatic next runtime.

## Context

Long-running flows need async execution and progress visibility. Runtime choice can evolve, but client contracts must remain stable.

## Decision

Freeze task API contract and lifecycle first. Implement LocalTaskRunner as the first backend, then add Celery/Redis under the same contract.

## Consequences

1. UI and client code can integrate once.
2. Runtime backend can be switched with lower risk.
3. Requires strict state transition tests and compatibility checks.

## Update (2026-10): duplicates and orphans

- Submitting exactly the same request (type, owner, payload) while the first is still queued or running returns that
  task instead of creating another (`core/async_tasks.py:find_active_duplicate`); a user may have 3 active tasks.
- A queued task that no runner has started after 60 seconds (its process restarted, or all threads were busy) is
  handed to any live runner by the maintenance loop (`LocalTaskRunner.requeue_orphans`); the conditional
  `mark_task_running` transition lets exactly one runner execute it. The 30-minute expiry stays as the last resort.

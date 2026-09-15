# Phase 3 — Celery Beat scheduling and task idempotency

## Root cause

Beat previously emitted the publishing, polling, rescoring, and approval
maintenance jobs at the same minute boundary. Timing alone also provided no
protection against duplicate Beat instances, delayed delivery, or a task that
ran longer than its interval.

## Changes

- Added Beat countdown offsets: publishing at the boundary, polling at +10s,
  rescoring at +20s, and stale-approval expiry at +30s.
- Added task expiry windows so stale maintenance messages are discarded rather
  than creating a late burst.
- Added Redis token locks with compare-and-delete release semantics for:
  `poll_sources`, `rescore_all_tenants`, `publish_due_jobs`, per-tenant
  `sync_analytics`, and per-tenant trending digests.
- Lock failures propagate instead of allowing unsafe unlocked execution.
- Publishing retains its existing database claim, attempt-key, and provider
  idempotency protections; the Redis lock only prevents unnecessary overlap.

## Before / after

| Behavior | Before | After |
|---|---|---|
| Maintenance timing | Same minute boundary | 0s / +10s / +20s / +30s offsets |
| Duplicate Beat delivery | Could overlap | Second copy skips while lock is held |
| Publish duplicate protection | DB claim/idempotency only | DB claim/idempotency plus scheduler lock |
| Lock release | Not applicable | Token-checked Redis release |

## Validation

Added scheduler and lock simulation tests. Focused Phase 3, Celery policy,
worker runtime, and recovery tests pass. Live Redis overlap validation was not
possible because local services were not running.

## Files changed in Phase 3

- `backend/workers/celery_app.py`
- `backend/workers/task_lock.py`
- `backend/workers/task_defs/{analytics,ingestion,publishing,stories,trending}.py`
- `backend/tests/test_phase3_scheduling.py`
- `docs/phase3-beat-idempotency.md`


# Phase 2 — Celery worker, database pool, and queue architecture

## Baseline and root cause

The local `Procfile.dev` worker consumed all eight queues with a gevent
concurrency of 16. Worker settings provide a database pool of 2 connections
plus 2 overflow connections, so the maximum worker checkout budget is 4.

Static task inspection found 18 registered task policies: 17 use the async
worker/database execution path and one (`send_email_task`) is SMTP-only. The
previous worker concurrency could therefore reserve more simultaneous
database-backed work than the worker pool was designed to support.

Live CPU, RAM, pool-wait, queue-latency, throughput, and failure-rate metrics
could not be collected because the local Celery, Redis, and database services
were not running.

## Changes

- Local worker concurrency is now 4, matching the configured worker pool
  ceiling.
- Local prefetch is explicitly 1 so long-running tasks do not reserve extra
  messages and increase queue latency.
- Local startup remains one simple worker consuming all queues.
- Existing workload queue groups remain available for production separation:

  - `io`: `ingestion,enrichment,email,approvals`, concurrency 4
  - `llm`: `generation`, concurrency 2
  - `media`: `video`, concurrency 1
  - `publishing`: `publishing`, concurrency 2
  - `db`: `analytics`, concurrency 2

Production should run those groups as separate Celery worker processes so
video/media and generation workloads cannot starve publishing, approvals,
email, ingestion, or analytics. The `celery_worker_argv()` helper emits the
queue, concurrency, prefetch, and hostname arguments for each group.

## Before / after

| Item | Before | After |
|---|---:|---:|
| Local worker concurrency | 16 | 4 |
| Worker DB pool slots | 4 | 4 |
| Maximum configured DB-backed task concurrency | 16 local worker slots | 4 local worker slots |
| Local prefetch | implicit/default | 1 |

The change removes the known 4-versus-16 resource mismatch without enlarging
the database pool.

## Files changed in Phase 2

- `Procfile.dev`
- `backend/tests/test_phase2_worker_architecture.py`
- `docs/phase2-worker-architecture.md`


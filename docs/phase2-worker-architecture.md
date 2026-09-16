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

- Local `Procfile.dev` runs **specialized workers** aligned with docker-compose
  Phase 14 groups (`worker_io`, `worker_llm`, `worker_media`,
  `worker_publishing`, `worker_db`) so video/LLM work cannot starve
  publishing, approvals, email, or ingestion.
- Media uses `--pool=prefork --concurrency=1`; I/O/LLM/publishing/db use gevent
  with workload-appropriate concurrency and `--prefetch-multiplier=1`.
- Frontend and Celery processes wait on `GET /api/v1/health/live` before start
  to avoid startup `ECONNREFUSED` races.
- Alembic `upgrade head` runs only from the backend process (plus
  `make migrate` before honcho), not from every worker/beat process.
- `celery_worker_argv()` remains the source of queue/concurrency fragments for
  production compose.

## Before / after

| Item | Before | After |
|---|---|---|
| Local worker shape | one gevent worker, all queues, concurrency 4 | five specialized workers |
| Media pool | gevent (shared) | prefork concurrency 1 |
| Frontend start | immediate with backend | waits for `/health/live` |
| Alembic on startup | backend + worker + beat | backend only |

## Files changed in Phase 2

- `Procfile.dev` (specialized workers + readiness gates)
- `Makefile.local` (project-scoped process cleanup)
- `backend/tests/test_phase2_worker_architecture.py`
- `docs/phase2-worker-architecture.md`


# Phase 12 — Before/After Performance Report

Date: 2026-09-15  
Environment: Linux x86_64, Python 3.12, Node 22.22.2, disposable PostgreSQL
container on `:55432`. Redis, MinIO, API, and Celery were not available during
the final validation.

## Executive result

The validated code paths show the intended concurrency, queue, request-path,
and bundle improvements. Live service latency, queue depth, resource usage,
and named Celery task execution remain unverified because the local dependency
stack could not start (`minio/minio:latest` was unavailable).

## Async worker reliability

| Measure | Before | After |
|---|---|---|
| Concurrent async bridge | 2 successes, 1 `event loop is already running`; un-awaited coroutine warning | 3/3 simultaneous operations succeeded; 0 failures |
| `poll_sources_task`, `rescore_all_tenants_task`, `publish_due_jobs_task` | No live worker was running; task failure count unavailable | Registered with the corrected runtime and policies; live execution/failure count unavailable without Redis/DB |
| `Task destroyed`, `event loop closed`, coroutine warnings | Not measured live; one un-awaited coroutine reproduced | None emitted by the executed concurrency regression |

## Health checks

| Endpoint | Before | After |
|---|---|---|
| `/health/live` | Connection refused; API was down | Live HTTP result not captured; API could not start without the local stack |
| `/health/ready` | Connection refused; API was down | Dependency checks are bounded to 750 ms and tested concurrently; live latency unverified |

The readiness unit test completed three 30 ms dependency checks in under 150 ms,
confirming parallel execution. The production target remains `<1 s` under
normal local operation.

## HTTP error contracts

| Failure mode | Before | After validation |
|---|---|---|
| `GET /metrics` | 404 | Root metrics route is registered; app/OpenAPI smoke and health contract tests pass |
| Cluster detail identifier | 422 risk from list/detail mismatch | Route-parity and API contract tests pass |
| Audit logs | 400 risk | API contract tests pass |
| Startup `ECONNREFUSED` | Frontend could start before the API | Startup now polls backend liveness; live startup noise unverified |

No runtime error-rate count is claimed because no API process was available.

## Duplicate requests and Web Vitals

| Surface | Before | After |
|---|---|---|
| Auth refresh | Static single-flight guard present; runtime count unavailable | Single-flight behavior covered by frontend client tests |
| Briefs, content jobs, approvals, source health/articles | Runtime counts unavailable | TanStack Query keys and query-hook regression tests pass; runtime counts unavailable |
| Web Vitals | One initialization call by static inspection | Registration and telemetry tests pass; browser runtime unverified |

## Ingestion request path

| Measure | Before | After |
|---|---:|---:|
| Manual ingestion request | Approximately 1.5 s while connector I/O ran inline | Numeric runtime latency unavailable; request now performs a short enqueue transaction and returns `202` |
| Worker processing | Included in request latency | Moved to `ingest_source_task`; processing duration is observable but not measured without Celery |

## Worker resources

| Resource | Before | After |
|---|---:|---:|
| Local worker concurrency | 16 gevent slots | 4 slots |
| Worker DB pool capacity | 2 + 2 overflow = 4 | 2 + 2 overflow = 4 |
| Local prefetch | Implicit/default | 1 |
| Specialized concurrency | One shared worker | IO 4, LLM 2, media 1, publishing 2, DB 2 |
| CPU/RAM/queue latency | Not measured; worker was absent | Not measured; workers could not start without Redis |

The final concurrency values fit the four-slot worker DB budget and keep
long-running workloads from reserving excess messages. They are configuration
and architecture values, not live utilization measurements.

## Seeded benchmark comparison

The deterministic harness uses 10 samples and seed `20260915`. Values below
are p95 latency in milliseconds; the post-change run was executed on the same
local harness.

| Scenario | Before | After |
|---|---:|---:|
| Source ingestion normalization | 38.494 | 41.481 |
| Duplicate detection | 8.620 | 0.283 |
| Source health | 0.228 | 0.240 |
| Story clustering | 1.709 | 1.920 |
| Content generation helpers | 0.409 | 0.358 |
| Publishing claim recovery | 0.111 | 0.107 |
| Analytics sync helpers | 0.421 | 0.334 |
| Major list serialization | 1.761 | 31.162 |

These are CPU/memory microbenchmarks, not end-to-end API timings. The large
post-change list-serialization sample is noisy and should not be treated as a
database regression; production SQL query budgets remain covered by the
baseline contract and architecture tests.

## Validation and release stance

- Frontend unit tests: 65/65 passed.
- TypeScript check and production build: passed.
- Backend worker/architecture/parity focused gate: passed (29 tests).
- Playwright discovery: 10 tests listed; execution blocked by missing browser binaries.
- Full live-stack and named-task load validation: not verified.

Status: **ready with known validation gaps**, not a full production performance
sign-off. Re-run the live endpoint, Celery, Redis, and Playwright sections in a
CI/staging environment with PostgreSQL, Redis, MinIO, and browser binaries.

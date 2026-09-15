# Phase 7 — Source ingestion request-path optimization

## Root cause

`POST /sources/{source_id}/ingest` and `/manual-poll` called `run_ingestion_workflow()` directly from FastAPI. That workflow performs the external connector fetch and parsing before returning, so the request held the client open for the observed roughly 1.5 seconds.

## Changes

- Both source-trigger endpoints now create or reuse a tenant-scoped queued `SourceFetchRun`, enqueue the existing `ingest_source_task`, and return HTTP 202.
- The response includes `status`, `source_id`, `fetch_run_id`, and the Celery `task_id`.
- The worker accepts `fetch_run_id` and atomically claims a queued run as `running`; it does not create a second ledger row. Existing scheduled fan-out remains compatible and continues to create its run in the worker.
- Repeated requests while a source run is queued/running reuse the existing run instead of starting another manual fetch.
- Added `GET /sources/fetch-runs/{fetch_run_id}` for durable status polling, tenant-scoped through the authenticated membership.
- Queue failure marks the durable run failed and returns 503, allowing a later trigger to retry.

## Measurement

Before: the API request synchronously performed connector I/O and returned only after ingestion work completed (observed baseline: approximately 1.5 seconds).

After: the request path performs validation, one short database enqueue transaction, and Celery submission; connector I/O runs on the ingestion worker. A runtime latency benchmark was not run in this environment, so no numeric post-change latency claim is made.

Regression coverage verifies that the trigger routes enqueue rather than call the workflow inline, and that the worker receives and claims a queued fetch run. Existing split-phase ingestion and Celery policy tests continue to pass.

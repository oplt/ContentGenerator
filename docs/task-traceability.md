# Task traceability (ops Phase 14)

## Problem

Successful Celery ingestion results showed `task_id: None` even though Celery
had assigned a real task UUID. Operators could not join:

HTTP enqueue → Celery task → `source_fetch_runs` → LLM calls → content/publish jobs.

## Meaning of `task_id`

On `IngestionTriggerResponse.task_id` (and Celery task return payload), **`task_id`
is the Celery task UUID** — not `operations.task_executions.id`.

HTTP enqueue pre-assigns that UUID into `fetch_run.metadata.celery_task_id` and
passes it to `apply_async(task_id=...)`, so the 202 response already had a value.
The worker success path rebuilt the response without copying it.

## Fix

1. `run_ingestion_workflow(..., celery_task_id=, correlation_id=)` stamps both onto
   `fetch_run.metadata` during prepare (create or claim).
2. Every workflow result goes through `_stamp_task_id`.
3. `ingest_source_task` always sets `payload["task_id"] = request.id` on return.
4. Manual queue also stores HTTP `correlation_id` on the fetch run.
5. Fetch-run API responses expose `celery_task_id` + `correlation_id` from metadata.
6. Generation Celery results include `task_id` and persist it on
   `content_jobs.provider_metadata`.

## Correlation chain

| Hop | Identifier |
|---|---|
| HTTP | `X-Correlation-ID` / request state `correlation_id` |
| Enqueue | `fetch_run.metadata.celery_task_id` + `correlation_id` |
| Celery | `request.id` (== pre-assigned id for manual ingest) |
| Ops ledger | `task_executions.celery_task_id` + `correlation_id` |
| Fetch run | `source_fetch_runs.id` + metadata trace fields |
| Logs | structlog context: `correlation_id`, `celery_task_id`, `fetch_run_id`, `source_id` |
| Content job | `provider_metadata.celery_task_id` + return `task_id` |
| Publishing | claim `worker_id` = Celery task id |

## Tests

`backend/tests/test_phase14_task_traceability.py`

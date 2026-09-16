# Phase 15 — Run Inspection and Operator Recovery

Make workflow operations usable in production without mutating successful history.

## Run detail (GET `/workflows/runs/{id}`)

Returns redacted inspection payload:

| Run | Node |
|-----|------|
| status, trigger, automation name, brand name, version number, correlation ID, timestamps | status, attempt, duration_ms, input/output/error (redacted), TaskExecution ids, claim lease summary fields, next_attempt_at, waiting_reason |
| | `can_resume` / `can_retry` flags (resume/claim tokens never returned) |

Sensitive keys (`*token*`, `*secret*`, `api_key`, …) become `[redacted]`.

## Controlled actions

| Action | Endpoint | Guard |
|--------|----------|-------|
| Retry node | `POST .../runs/{id}/nodes/{node_id}/retry` | FAILED only; SUCCEEDED → 409 |
| Retry from failed | `POST .../runs/{id}/retry-from/{node_id}` | FAILED only; ancestors untouched; descendants reset to PENDING |
| Cancel workflow | `POST .../runs/{id}/cancel` | not SUCCEEDED; preserves SUCCEEDED nodes |
| Resume wait | `POST .../runs/{id}/nodes/{node_id}/resume` | WAITING + server-held resume_token |
| Inspect approval / PublishingJob | UI links from `approval_request_id` / `job_ids` | read-only |

Retry keeps prior `output_json` on the failed node so approval/publish idempotency hooks still apply. Celery revoke + `cancellation_requested` for active nodes: see [phase16-cancellation.md](phase16-cancellation.md).

## UI

`WorkflowRunDetailPage` + `WorkflowRunNodeCard` — operator meta, per-node I/O, recovery buttons.

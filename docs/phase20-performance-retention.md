# Phase 20 — Performance and Retention

Hot-path indexes plus age-based scrubbing of large historical payloads.

## Indexes (Alembic `d2e3f4a5b6c7`)

| Index | Purpose |
|-------|---------|
| `ix_automations_due_schedule_next_run_at` | due automations (existing Phase ops) |
| `ix_workflow_waits_pending_wake_at` | due durable waits |
| `ix_workflow_node_runs_ready_run_created_at` | READY nodes by run |
| `ix_workflow_node_runs_expired_claims` | expired RUNNING/QUEUED claims |
| `ix_workflow_runs_tenant_status_created_at` | runs by tenant/status/date |
| `ix_workflow_node_runs_tenant_id_run_id` | nodes by run (existing) |
| `ix_publishing_jobs_tenant_social_account_created_at` | publishing by account |
| `ix_publishing_jobs_approval_request_id` | publishing ↔ approval (run linkage) |
| `ix_approval_requests_pending_expires_at` | approvals awaiting / expiry |
| `ix_workflow_node_runs_finished_at_terminal` | retention scan |
| `ix_task_executions_created_at` | TaskExecution retention |
| `ix_webhooks_inbox_status_received_at` | webhook payload retention |

ORM `__table_args__` mirror these indexes.

## EXPLAIN

Against Postgres with representative data:

```bash
DATABASE_URL=postgresql+asyncpg://... \
  PYTHONPATH=. backend/.venv/bin/python backend/scripts/explain_phase20_queries.py

PHASE20_EXPLAIN_ANALYZE=1 PYTHONPATH=. backend/.venv/bin/python \
  backend/scripts/explain_phase20_queries.py
```

Expect index scans / bitmap index scans on the indexes above (not seq scans on large tables).

## Retention policy

Celery beat: `workflow-retention-hourly` → `run_workflow_retention_task`.

| Target | Action | Default age | Setting |
|--------|--------|-------------|---------|
| Terminal node `input_json` / `output_json` | Scrub to `_retention` stub | 30d | `WORKFLOW_RETENTION_NODE_PAYLOAD_DAYS` |
| Finished `TaskExecution` | Delete row | 14d | `WORKFLOW_RETENTION_TASK_EXECUTION_DAYS` |
| Processed webhook inbox `payload` | Scrub stub (keep row) | 14d | `WORKFLOW_RETENTION_WEBHOOK_PAYLOAD_DAYS` |
| `audit_logs` | **Never** deleted by this job | — | — |

Optional archive before scrub:

* `WORKFLOW_RETENTION_ARCHIVE_TO_STORAGE=true`
* Object key: `retention/{kind}/tenants/{tenant_id}/{id}.json`
* Requires configured MinIO/S3 (`STORAGE_*`)

Disable: `WORKFLOW_RETENTION_ENABLED=false`.

Metric: `cg.operation.*` with `operation=workflow.retention`.

## Tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q \
  tests/test_workflow_phase20_perf_retention.py \
  tests/test_workflow_query_indexes.py \
  tests/test_phase3_scheduling.py
```

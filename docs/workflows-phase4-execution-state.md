# Workflow Domain — Phase 4 (Execution State)

Durable orchestration state separate from Celery telemetry.

## Models

| Table | Role |
|-------|------|
| `workflow_runs` | Business run (queued/running/waiting/succeeded/failed/cancelled) |
| `workflow_node_runs` | Per-node state + optional `task_execution_id` |
| `task_executions` | Unchanged Celery/infra telemetry |

`WorkflowNodeRun.task_execution_ids` holds extra telemetry links when a node spans retries.

## Migration

`e1f2a3b4c5d6_workflow_execution_state` (reversible). Composite tenant FKs to definition/version/automation/brand.

## API

* `GET /api/v1/workflows/runs`
* `GET /api/v1/workflows/runs/{run_id}` (includes node runs)

## Next

Phase 5 — minimal linear engine that creates/updates these rows.

# Phase 16 — Cancellation

Cancellation is durable **state management**, not history deletion.

## Semantics

```text
WorkflowRun RUNNING / WAITING / QUEUED / FAILED
        ↓ cancel
     CANCELLED

PENDING / READY / WAITING / FAILED nodes → CANCELLED
QUEUED / RUNNING (active) nodes:
  • cancellation_requested = true
  • TaskExecution.cancellation_requested = true (when linked)
  • Celery revoke(terminate=False) when worker_task_id present
  • node status → CANCELLED
SUCCEEDED nodes → unchanged (published work stays recorded)
```

Irreversible side effects (e.g. a publish that already SUCCEEDED) are never undone.

## Cooperative workers

`execute_claimed_node_run`:

1. If run already terminal/cancelled → abort queued/running claim row
2. `begin_node_execution` refuses `cancellation_requested`
3. Pre-execute check via `should_abort_node`
4. Post-execute: SUCCEEDED wins the race; otherwise cancel sticks

`finalize_run_status` will not reopen a CANCELLED run.

## API

`POST /workflows/runs/{run_id}/cancel` (Phase 15 surface; Phase 16 completes Celery + flags).

## Migration

`b0c1d2e3f4a5_workflow_node_cancellation.py` — `workflow_node_runs.cancellation_requested`

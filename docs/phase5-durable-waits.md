# Phase 5 — durable wait / delay

Roadmap: `prompt.txt` Phase 5.

## Problem

Delay/wait previously treated Celery `countdown`/`ETA` as the timer.
That fails across Redis flush, worker loss, and long sleeps.

## Design

`WorkflowWait` is the authoritative deadline ledger:

| Field | Role |
|-------|------|
| `wake_at` | Postgres-owned due time |
| `wait_type` | `delay` \| `event` |
| `event_key` | Provider/correlation lookup (pending unique) |
| `resume_token` | Links to `WorkflowNodeRun` |
| `timeout_action` | `fail` \| `continue` for event timeouts |
| `status` | `pending` → `resolved` |

### Timer flow

1. Delay/wait node returns `WAITING`
2. Engine persists `WorkflowWait` (`wait_persist.py`)
3. Optional Celery fast wake (`schedule_fast_wake`) — not authoritative
4. Beat task `wake_due_workflow_waits_task` every minute:
   - `SELECT … WHERE status=pending AND wake_at <= now() FOR UPDATE SKIP LOCKED`
   - resolve atomically → enqueue `resume_workflow_waiting_node_task`

### Event waits

`POST /workflows/resume` accepts `event_key` (preferred for providers) or
`resume_token`. Event resolve is atomic and deduped.

## Files

- `run_models.WorkflowWait` + Alembic `e7f8a9b0c1d2`
- `wait_store.py` / `wait_persist.py` / `wait_recovery.py`
- `wake_due_workflow_waits_task`
- Tests: `test_workflow_phase5_durable_waits.py`

## Next phase

**Phase 7 — Harden scheduler lifecycle**

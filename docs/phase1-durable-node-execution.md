# Phase 1 — durable node execution and atomic claiming

Roadmap: `prompt.txt` Phase 1.

## Architecture

```text
API / scheduler
  → WorkflowEngine.advance()          # orchestration only
      → claim_ready_node()            # READY → QUEUED + claim lease
      → enqueue execute_workflow_node_task
Celery worker
  → execute_workflow_node_task        # exactly one WorkflowNodeRun
      → begin_node_execution (QUEUED → RUNNING, TaskExecution link)
      → execute_ready_node
      → complete_node / clear lease
      → advance() again for newly READY nodes
Beat
  → recover_stale_workflow_node_runs_task
      → requeue READY or fail after max_attempts
```

PostgreSQL is the source of truth. Celery is delivery only.

## Schema (migration `b4c5d6e7f8a9`)

`workflow_node_runs` gains:

- `claim_token`, `claim_expires_at`, `claimed_at`
- `worker_task_id`, `last_heartbeat_at`
- `next_attempt_at`, `execution_key`

Indexes: status+claim_expires_at; unique partial on claim_token.

## Config

- `WORKFLOW_CLAIM_LEASE_SECONDS` (default 900)
- `WORKFLOW_CLAIM_RECOVERY_BATCH_SIZE` (default 50)
- `WORKFLOW_INLINE_NODE_EXECUTION` (default **False** in production; tests force True via `conftest.py`)

## Acceptance

| Criterion | Status |
|-----------|--------|
| Concurrent claims cannot double-execute | Covered by `test_two_claimers_cannot_claim_same_ready_node` |
| Stale RUNNING recovered | `test_stale_running_node_is_requeued_by_recovery` |
| Max attempts → FAILED | `test_stale_node_fails_after_max_attempts` |
| API does not inline domain nodes | `engine.advance` has no `execute_ready_node`; Celery path enqueues |
| TaskExecution linked | `test_execute_claimed_node_links_task_execution_id` |
| Phase 0 gap xfails for P1 | Cleared in `test_workflow_production_gaps.py` |

## Files

- Models / migration: `run_models.py`, `b4c5d6e7f8a9_workflow_node_claim_lease.py`
- Claims: `run_repository.py` (`claim_ready_node`, `renew_node_claim`, `release_node_claim`, `complete_node`, `fail_node`)
- Orchestration: `engine.py`, `engine_dispatch.py`, `engine_node_task.py`, `node_recovery.py`
- Workers: `execute_workflow_node_task`, `recover_stale_workflow_node_runs_task` (+ beat every minute)
- Tests: `test_workflow_node_claims.py`

## Remaining (Phase 2+)

- Typed retry classification (`last_error`, `error_class`) and exponential backoff
- Port/binding data flow (remove node_type switches in `engine_inputs.py`)
- Side-effect idempotency keys beyond `execution_key`

## Next phase

**Phase 2 — Activate the retry model**

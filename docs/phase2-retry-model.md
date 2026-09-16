# Phase 2 — activate the retry model

Roadmap: `prompt.txt` Phase 2.

## Behavior

Node `retry_policy` metadata is now enforced at execution time:

1. Classify failures into `ErrorClass` (`transient`, `rate_limited`, `timeout`,
   `provider_unavailable`, `validation`, `permanent`, `authentication`, `policy`).
2. If `should_retry(error_class, attempt, policy)`:
   - set `WorkflowNodeRun` back to `READY`
   - persist `last_error`, `error_class`, `error_json`, `next_attempt_at`
   - clear claim lease
   - schedule `advance_workflow_run_task` after exponential backoff (+ jitter)
3. Otherwise mark `FAILED` permanently (no blind retries of validation/auth/policy).

Backoff:

```text
delay = min(max_backoff, base * 2^(attempt - 1)) ± jitter
```

Defaults: `backoff_seconds=2`, `max_backoff_seconds=300`,
`retry_on=[transient, rate_limited, timeout, provider_unavailable]`.

PostgreSQL remains the source of truth — Celery countdown is only a wake-up.

## Schema (migration `c5d6e7f8a9b0`)

- `workflow_node_runs.last_error` (Text)
- `workflow_node_runs.error_class` (String 64)
- index `(status, next_attempt_at)`

## Idempotency

- `execution_key = {run_id}:{node_id}:v{version}[:iteration]`
- Publish inputs receive `idempotency_key` from `execution_key` when missing
- Approval redelivery reuses existing `approval_request_id` on the node run output

## Files

- `node_retry.py` — classify / backoff / schedule / publish key injection
- `engine_execute.py` — `_persist_failure` retry vs fail
- `engine_node_task.py` — clear claim + schedule follow-up advance
- `node_recovery.py` — lease expiry uses same retry rules + backoff
- `nodes/base.py` — `max_backoff_seconds` + broader default `retry_on`
- Tests: `test_workflow_retry.py`

## Remaining

- Phase 3: port/binding input routing (remove node_type switches)
- Stronger media-asset idempotency keys where generators support them

## Next phase

**Phase 3 — Replace hardcoded engine input routing with real DAG data flow**

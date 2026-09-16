# Phase 19 — Observability

Extends Phase 16 workflow metrics/logs. Does **not** replace `cg.operation.*`.

## Prompt metric aliases

| Prompt name | `cg.operation.*` `operation=` | Notes |
|-------------|-------------------------------|-------|
| `workflow_runs_total` | `workflow.run` | all outcomes incl. started |
| `workflow_runs_failed` | `workflow.run` | filter `outcome=failed` |
| `workflow_run_duration` | `workflow.run` | histogram |
| `workflow_node_runs_total` | `workflow.node` | `stage=<node_type>` |
| `workflow_node_duration` | `workflow.node` | histogram |
| `workflow_node_retries` | `workflow.node` | filter `event=retry` |
| `workflow_node_claim_expirations` | `workflow.node.claim_expiration` | recovery path |
| `workflow_node_stale_recoveries` | `workflow.node.stale_recovery` | `outcome=requeued\|failed` |
| `workflow_wait_duration` | `workflow.wait` | `stage=<wait_type>` |
| `workflow_approval_duration` | `workflow.approval_wait` | resume path |
| `workflow_scheduler_occurrences` | `workflow.scheduler.occurrence` | |
| `workflow_scheduler_lag` | `workflow.scheduler.lag` | histogram ms |
| `workflow_publish_jobs` | `workflow.publish` | success counts job_ids |
| `workflow_publish_failures` | `workflow.publish` | filter `outcome=failure` |
| `workflow_llm_calls` | `workflow.llm` | text/canonical/summarize/… |
| `workflow_media_generation` | `workflow.media` | image/video/tts/chess |

Alias map: `PHASE19_METRIC_ALIASES` in `backend/modules/workflows/observability.py`.

Snapshot: `GET /api/v1/health/metrics`.

## Log / span identifiers (not metric labels)

Bound via `bind_workflow_run_context` / `ids_for_logs`:

* `workflow_definition_id`
* `workflow_version_id` + optional `workflow_version` (integer)
* `automation_id`
* `node_type` / `node_id` / `attempt`
* `workflow_run_id`, `tenant_id`, `correlation_id` — **logs/traces only**

## Hooks

| Event | Hook |
|-------|------|
| Run start / finish | `engine.start_run`, `finalize_run_status` |
| Node finish | `engine_execute` |
| Approval wait | `engine_resume` |
| Claim expiry / stale recovery | `node_recovery.recover_stale_workflow_node_runs` |
| Durable wait resolve | `wait_recovery.wake_due_workflow_waits` |
| Scheduler tick | `AutomationScheduler.tick` |

## Deferred

AI token usage / estimated AI cost / media cost — inference adapters do not yet
expose durable token or dollar fields. When available, emit under low-cardinality
`provider` + `model` only (never prompts).

## Tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q \
  tests/test_workflow_phase19_observability.py \
  tests/test_workflow_observability.py
```

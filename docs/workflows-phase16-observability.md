# Workflow Domain — Phase 16 (Observability)

## Identity on every run/node

Already on models; also bound into structlog context at execute time:

* `tenant_id`, `correlation_id`
* `workflow_run_id`, `workflow_definition_id`, `workflow_version_id`
* `automation_id`, `brand_id`
* `node_id`, `node_type`, `attempt`

IDs stay on **logs/spans only** — never metric labels.

## Metrics (`cg.operation.*`)

| `operation` | Meaning |
|-------------|---------|
| `workflow.run` | start + terminal duration/outcome |
| `workflow.node` | node duration; `stage=<node_type>`; `event=retry` when attempt>1 |
| `workflow.approval_wait` | wait time from node start → resume |
| `workflow.media` | media node duration alias |
| `workflow.publish` | publish node failure counter |

Snapshot: `GET /api/v1/health/metrics`.

## Never logged

OAuth/refresh tokens, provider secrets, webhook secrets — redacted by `drop_sensitive_log_keys`; not in log-context allowlist.

## Hooks

* `engine.start_run` → `log_workflow_run_started`
* `engine_execute.execute_ready_node` → bind + `record_workflow_node_finished`
* `engine_status.finalize_run_status` → `record_workflow_run_finished`
* `engine_resume.resume_waiting_node` → `record_approval_wait`

LLM cost metering: not available yet (no cost fields on inference) — deferred.

## Phase 19

Extended counters/histograms for claim expirations, stale recoveries, durable waits,
scheduler lag/occurrences, publish job counts, and workflow LLM calls. See
[phase19-observability.md](phase19-observability.md).

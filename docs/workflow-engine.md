# Workflow engine

Durable linear / control-flow execution over `WorkflowRun` + `WorkflowNodeRun`.

Code: `backend/modules/workflows/engine*.py`, `compiler*.py`, `config_*.py`.

## Start → advance loop

```mermaid
sequenceDiagram
  participant API
  participant Engine
  participant DB
  participant Node
  participant Celery

  API->>Engine: start_run(version, payload, flags)
  Engine->>DB: validate published version + compile
  Engine->>DB: snapshot config (no secrets)
  Engine->>DB: insert run + node runs (roots READY)
  loop until waiting / failed / done
    Engine->>Node: execute READY
    Node-->>Engine: SUCCEEDED / WAITING / FAILED
    Engine->>DB: persist I/O + unlock
  end
  Note over Engine,Celery: WAITING releases workers; resume later
  API->>Engine: resume(token, outcome) / advance
```

1. Load published `WorkflowVersion`
2. Enrich compile context (accounts / capabilities)
3. Compile graph — reject invalid
4. Build immutable `context_snapshot`
5. Create run + node rows
6. Execute READY nodes; stop on WAITING or FAILED
7. Finalize SUCCEEDED when all required nodes terminal

## Versioning

* Edit draft via `PUT .../draft` (sanitized graph).
* `POST .../publish` creates immutable `WorkflowVersion` and points `current_version_id`.
* Historical runs keep their `workflow_version_id` forever.
* Never mutate a published graph in place.

## Configuration precedence

Later layers win (secrets stripped):

1. Node `ConfigSchema` defaults  
2. Workflow node `config`  
3. Brand / BrandProfile  
4. Automation settings / node_overrides  
5. Account / target overrides  
6. Run / trigger / `run_config`

Frozen into `resolved_node_configs` at start. Detail: [workflows-phase8-config-resolution.md](workflows-phase8-config-resolution.md).

## Idempotency

| Boundary | Mechanism |
|----------|-----------|
| Start | Same `correlation_id` → return existing run |
| Scheduler | `UNIQUE(automation_id, scheduled_occurrence)` + `sched:{id}:{occurrence}` |
| Node | Skip re-exec of SUCCEEDED / WAITING |
| Publish | Default `idempotency_key=wf-publish-{run_id}` |

## Dry-run / test flags

| Flag | Effect |
|------|--------|
| `dry_run` | Force publish dry-run; `trigger_type=dry_run` |
| `mock_generation` | Deterministic mock LLM/media outputs |
| `simulate_approval` | Auto-resume WAITING approvals as approved |

Single-node: `POST /workflows/nodes/{type}/test`.

## Debugging failed runs

1. Open `/dashboard/runs/{id}` — node statuses, attempts, error_json, I/O.
2. Check `WorkflowRun.error_message` + failed node `error_json.code`.
3. Confirm version checksum vs intended graph.
4. Inspect snapshot: `resolved_node_configs`, `accounts`, `testing`.
5. Logs: structured `cg.operation.*` / workflow bind fields (`tenant_id`, `correlation_id`, node type) — no tokens.
6. Metrics: run/node duration, publish failures — [observability/metrics.md](observability/metrics.md).
7. Retry: reset failed node → `READY`, run → `RUNNING`, call `advance` (bumps `attempt`).

## Related

* [workflows-phase5-engine.md](workflows-phase5-engine.md)
* [workflows-phase12-control-flow.md](workflows-phase12-control-flow.md)
* [workflows-phase15-testing.md](workflows-phase15-testing.md)
* [workflows-phase16-observability.md](workflows-phase16-observability.md)

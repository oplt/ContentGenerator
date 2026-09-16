# Workflow Domain — Phase 5 (Minimal Engine)

Linear in-process engine over durable `WorkflowRun` / `WorkflowNodeRun` rows.

## Behavior

1. Load published `WorkflowVersion`
2. Compile/validate graph
3. Create run + node runs (roots = READY)
4. Execute READY nodes via registry
5. Persist outputs into `context_snapshot.node_outputs`
6. Unlock downstream when upstream SUCCEEDED
7. Stop on WAITING (approval) or FAILED
8. Mark run SUCCEEDED when all nodes terminal

## Modules

* `engine.py` — `WorkflowEngine.start_run` / `advance`
* `engine_inputs.py` — map trigger/upstream → node inputs
* `engine_ready.py` — READY unlock / terminal checks
* `engine_status.py` — finalize run status

## Idempotency

* Same `correlation_id` returns existing run
* SUCCEEDED / WAITING nodes are never re-executed
* Publish uses stable `idempotency_key=wf-publish-{run_id}` when unset

## API

* `POST /workflows/definitions/{id}/runs`
* `POST /workflows/runs/{id}/advance`

## Tests

`backend/tests/test_workflow_engine.py` — linear success, correlation idempotency, approval WAITING pause, unpublished reject.

## Next

Phase 6 — resume WAITING approval nodes without blocking workers.

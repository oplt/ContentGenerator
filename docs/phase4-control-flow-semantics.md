# Phase 4 — workflow control-flow semantics

Roadmap: `prompt.txt` Phase 4.

## Fixes

### Merge `mode=any`

`is_ready` no longer requires every predecessor to be SUCCEEDED/SKIPPED before
testing `any`. One SUCCEEDED arm is enough; siblings may stay PENDING/RUNNING/FAILED.

### Merge `mode=all`

Waits until every incoming branch is satisfied:

| Status | Counts as satisfied? |
|--------|----------------------|
| SUCCEEDED | yes |
| SKIPPED | yes (not failure) |
| FAILED / CANCELLED | no |
| PENDING / RUNNING / … | wait |

### SKIPPED

Conditional branch miss → `SKIPPED` + cascade. Join nodes (merge) unlock when
remaining arms are satisfied; SKIPPED ≠ FAILED for run finalization.

## Real fan-out

`fan_out` still normalizes `items`, then **spawns** one `WorkflowNodeRun` per item
on its single successor:

| Field | Value |
|-------|--------|
| `node_id` | successor graph id (unchanged) |
| `iteration_key` | immutable item key (`platform`, string id, or `i{n}`) |
| Unique | `(tenant_id, workflow_run_id, node_id, iteration_key)` |

Placeholder row (`iteration_key=""`) is marked SKIPPED (`superseded_by_fan_out`).

Graph stays immutable — no dynamic node ids.

### Merge of iterations

Merge collects predecessor outputs in stable `iteration_key` order (including
multi-iteration bodies after fan-out). Single-edge merge is allowed for iteration joins.

## Files

- `run_models.py` + Alembic `d6e7f8a9b0c1` — `iteration_key`
- `engine_ready.py` — merge any/all readiness
- `engine_fanout.py` — spawn / propagate iterations
- `engine_node_index.py` — multi-row index
- `engine.py` / `engine_execute.py` / `engine_unlock.py`
- Tests: `test_workflow_phase4_control_flow.py`

## Next phase

**Phase 6 — Harden automation / brand / account integrity**

# Workflow Domain — Phase 12 (Control-Flow Nodes)

Branching, durable pauses, merge — without holding Celery workers asleep.

## Nodes

| Node | Behavior |
|------|----------|
| `condition` | Eval bag field (`truthy`/`eq`/`gt`/…) → `output.branch`; edges must label `condition` |
| `fan_out` | Normalize items; spawn one `WorkflowNodeRun` per item (`iteration_key`) on successor |
| `merge` | Combine upstream outputs / iterations; `mode=all\|any` gates readiness |
| `delay` | Persist `WorkflowWait.wake_at`; optional Celery fast wake; beat scanner resumes |
| `wait` | Persist event wait (+ optional timeout); resume via token or `event_key` |

## Engine

* `engine_unlock.unlock_after_node_success` — branch match → READY; other arms → `SKIPPED` + cascade
* `is_ready` — `merge` `mode=any` needs ≥1 `SUCCEEDED` (siblings may still be open); `mode=all` needs every arm SUCCEEDED or SKIPPED
* `engine_fanout.materialize_fan_out_success` — per-item iterations; graph stays immutable
* Resume outcomes: `approved\|rejected\|expired\|elapsed\|received`
* Task: `resume_workflow_waiting_node_task`

## Phase 4 notes

See [phase4-control-flow-semantics.md](phase4-control-flow-semantics.md).

## Tests

`backend/tests/test_workflow_control_flow.py`,
`backend/tests/test_workflow_phase4_control_flow.py`

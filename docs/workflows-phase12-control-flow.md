# Workflow Domain — Phase 12 (Control-Flow Nodes)

Branching, durable pauses, merge — without holding Celery workers asleep.

## Nodes

| Node | Behavior |
|------|----------|
| `condition` | Eval bag field (`truthy`/`eq`/`gt`/…) → `output.branch`; edges must label `condition` |
| `fan_out` | Data-only list normalize (`items` / account ids); **one** unconditional successor |
| `merge` | Combine upstream outputs; `mode=all\|any` gates readiness |
| `delay` | `WAITING` + Celery `countdown`/`eta` → resume `elapsed` |
| `wait` | `WAITING` until `POST /workflows/resume` (`received`) or timeout `expired` |

## Engine

* `engine_unlock.unlock_after_node_success` — branch match → READY; other arms → `SKIPPED` + cascade
* `is_ready` — `merge` `mode=any` needs ≥1 `SUCCEEDED`
* Resume outcomes: `approved\|rejected\|expired\|elapsed\|received`
* Task: `resume_workflow_waiting_node_task`

## Non-goals

* Dynamic N parallel `WorkflowNodeRun` rows per fan-out (still one row per graph node_id)
* Complex expression language beyond field/operator/compare_to

## Tests

`backend/tests/test_workflow_control_flow.py`

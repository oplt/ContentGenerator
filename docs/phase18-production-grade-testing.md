# Phase 18 — Production-Grade Testing

Distributed-system regression scenarios for the workflow engine.

## Requirement matrix

| Scenario | Expected | Primary owners |
|----------|----------|----------------|
| Two workers claim same node | Exactly one claim | `test_workflow_node_claims`, `test_workflow_phase18_production_grade` |
| Celery task redelivery | One logical side effect | `test_workflow_phase18_production_grade` |
| Crash / expired claim | Requeue + retry | `test_workflow_node_claims`, Phase 18 |
| Publish redelivery | No duplicate publish jobs | Phase 18 + `test_workflow_strategy` + `test_publishing_idempotency` |
| Approval revise → approve | Resume once with revised content | Phase 18 + Phase 9 + approval resume |
| Durable delay + restart | Wait row survives; wake resumes | Phase 5 + Phase 18 |
| Scheduler double tick | One WorkflowRun | `test_workflow_scheduler` (+ PG) + Phase 18 |
| Branching | Condition / merge all|any / skip / fail | Phase 4 + Phase 18 |
| Tenant isolation | Cross-tenant run/resume/variant → not found | Domain models + Phase 18 |
| Chess Daily vertical | PGN → video → caption → approval → transform → multi dry-run publish | Phase 18 |
| Technology vertical | News → content → approval → variants → multi-account dry-run publish | Phase 18 |

Manifest: `backend/tests/test_workflow_phase18_regression_matrix.py`  
Behavioral suite: `backend/tests/test_workflow_phase18_production_grade.py`

## Commands

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q \
  tests/test_workflow_phase18_production_grade.py \
  tests/test_workflow_phase18_regression_matrix.py

# Broader workflow regression
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/test_workflow_*.py
```

## Notes

* Vertical E2Es use `dry_run` + `mock_generation` + `simulate_approval`; publish stays dry-run.
* Chess mock generation returns a complete `GenerateChessVideoOutput` shape (`testing_support.py`).
* Do not start Phase 19 until this suite is green.

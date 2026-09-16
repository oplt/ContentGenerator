# Workflow Domain — Phase 18 (Testing Strategy)

## Layers

| Layer | Scope | Location |
|-------|--------|----------|
| Unit | nodes, resolver, compiler checks, security scrub | `backend/tests/test_workflow_*.py` |
| Repository / domain | FK, tenant isolation, uniqueness | `test_workflow_domain_models.py`, `test_workflow_execution_state.py` |
| Engine / resume | linear advance, WAITING, correlation idempotency, retry attempt | `test_workflow_engine.py`, `test_workflow_approval_resume.py`, `test_workflow_strategy.py` |
| Scheduler | due tick + occurrence uniqueness | `test_workflow_scheduler.py`, `test_workflow_scheduler_pg.py` |
| Dry-run / node test | Phase 15 flags | `test_workflow_testing.py` |
| Production-grade distributed | claim, redelivery, crash, publish, revise, delay, branching, tenant, vertical E2E | `test_workflow_phase18_production_grade.py`, `test_workflow_phase18_regression_matrix.py` |
| Strategy gaps | publish key, retry, e2e dry-run, chess compile | `test_workflow_strategy.py` |
| Frontend unit | API helpers, canvas/editor graph, pages | `frontend/src/**/*.test.ts(x)` |
| E2E (mocked API) | list → create → runs monitor | `frontend/e2e/workflows.spec.ts` |

## Backend matrix ↔ owners

See [phase18-production-grade-testing.md](phase18-production-grade-testing.md) for the full Phase 18 prompt matrix.

| Requirement | Owning test(s) |
|-------------|----------------|
| Unit / node contract | `test_workflow_node_registry.py`, `test_workflow_media_nodes.py` |
| Compiler / DAG | `test_workflow_graph_compiler.py`, `test_workflow_control_flow.py` |
| Scheduler idempotency | `test_workflow_scheduler.py` |
| Approval resume | `test_workflow_approval_resume.py` |
| Engine | `test_workflow_engine.py` |
| Tenant isolation | `test_workflow_domain_models.py`, `test_workflow_execution_state.py`, `test_workflow_phase18_production_grade.py` |
| Publish idempotency | `test_workflow_strategy.py`, `test_workflow_phase18_production_grade.py` |
| Distributed claims / crash | `test_workflow_node_claims.py`, `test_workflow_phase18_production_grade.py` |
| Vertical E2E dry-run | `test_workflow_phase18_production_grade.py` |

## Commands

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_workflow_*.py -q
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_workflow_phase18_*.py -q
cd frontend && npm test -- --run src/api/workflows.test.ts src/features/workflows src/pages/WorkflowsPage.test.tsx src/pages/AutomationsPage.test.tsx src/pages/WorkflowRunsPage.test.tsx src/pages/WorkflowRunDetailPage.test.tsx
cd frontend && npx playwright test e2e/workflows.spec.ts
```

Regression manifest risk area: `workflow_automation`.

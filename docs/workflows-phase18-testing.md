# Workflow Domain — Phase 18 (Testing Strategy)

## Layers

| Layer | Scope | Location |
|-------|--------|----------|
| Unit | nodes, resolver, compiler checks, security scrub | `backend/tests/test_workflow_*.py` |
| Repository / domain | FK, tenant isolation, uniqueness | `test_workflow_domain_models.py`, `test_workflow_execution_state.py` |
| Engine / resume | linear advance, WAITING, correlation idempotency, retry attempt | `test_workflow_engine.py`, `test_workflow_approval_resume.py`, `test_workflow_strategy.py` |
| Scheduler | due tick + occurrence uniqueness | `test_workflow_scheduler.py` |
| Dry-run / node test | Phase 15 flags | `test_workflow_testing.py` |
| Strategy gaps | publish key, retry, e2e dry-run, chess compile | `test_workflow_strategy.py` |
| Frontend unit | API helpers, canvas/editor graph, pages | `frontend/src/**/*.test.ts(x)` |
| E2E (mocked API) | list → create → runs monitor | `frontend/e2e/workflows.spec.ts` |

## Backend matrix ↔ owners

| Requirement | Owning test(s) |
|-------------|----------------|
| Unit / node contract | `test_workflow_node_registry.py`, `test_workflow_media_nodes.py` |
| Compiler / DAG | `test_workflow_graph_compiler.py`, `test_workflow_control_flow.py` |
| Scheduler idempotency | `test_workflow_scheduler.py` |
| Approval resume | `test_workflow_approval_resume.py` |
| Engine | `test_workflow_engine.py` |
| Account capabilities | `test_workflow_platform_capabilities.py` |
| Config precedence | `test_workflow_config_resolver.py` |
| Tenant isolation | `test_workflow_domain_models.py`, `test_workflow_execution_state.py`, `test_workflow_strategy.py` |
| Retry (attempt bump) | `test_workflow_strategy.py` |
| Publish idempotency (`wf-publish-{run_id}`) | `test_workflow_strategy.py` (+ `test_publishing_idempotency.py`) |
| Security scrub / authz | `test_workflow_security.py` |
| Observability | `test_workflow_observability.py` |
| E2E dry-run happy path | `test_workflow_strategy.py::test_e2e_dry_run_happy_path` |
| Chess workflow compile | `test_workflow_strategy.py::test_chess_workflow_compiles` |

## Frontend matrix ↔ owners

| Requirement | Owning test(s) |
|-------------|----------------|
| Component / API helpers | `api/workflows.test.ts` |
| Editor graph / canvas | `features/workflows/editorGraph.test.ts`, `canvasGraph.test.ts` |
| Automations form | `pages/AutomationsPage.test.tsx` |
| Run monitor | `pages/WorkflowRunsPage.test.tsx`, `WorkflowRunDetailPage.test.tsx` |
| Workflows list/create | `pages/WorkflowsPage.test.tsx` |

## Canonical E2E path (backend)

1. published linear slice  
2. `dry_run` + `mock_generation` + `simulate_approval`  
3. real account IDs in compile context  
4. publish forced dry-run + `wf-publish-{run_id}`  
5. `WorkflowRun.status == succeeded`

UI E2E mirrors list/create/monitor with mocked `/api/v1/workflows/*`.

## Commands

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_workflow_*.py -q
cd frontend && npm test -- --run src/api/workflows.test.ts src/features/workflows src/pages/WorkflowsPage.test.tsx src/pages/AutomationsPage.test.tsx src/pages/WorkflowRunsPage.test.tsx src/pages/WorkflowRunDetailPage.test.tsx
cd frontend && npx playwright test e2e/workflows.spec.ts
```

Regression manifest risk area: `workflow_automation`.

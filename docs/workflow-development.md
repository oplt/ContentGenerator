# Workflow development

How to extend the workflow domain safely.

## Add a new node

1. **Implement** `WorkflowNode` subclass under `backend/modules/workflows/nodes/`:
   * `type`, `version`, category, display metadata
   * Pydantic `ConfigSchema` / `InputSchema` / `OutputSchema`
   * `required_capabilities`, `may_pause` if needed
   * `execute` → call existing domain service only
2. **Register** in `registry.py` / `IMPLEMENTED_SLICE` (or stub intentionally).
3. **Inputs**: extend `engine_inputs.resolve_node_inputs` if mapping from bag/trigger is non-trivial.
4. **Compiler**: ensure capabilities/ports make sense; add checks only if semantics are new.
5. **Tests**: contract + execute with mocked domain service (`test_workflow_*.py`).
6. **Frontend**: registry-driven palette picks it up; optional config form from JSON schema.
7. Keep modules ≤ line budget; extract helpers rather than growing god files.

### Anti-patterns

* Duplicating chess PGN/render, LLM policy, or publish claim logic inside the node.
* Putting secrets in `config` / graph JSON.
* Sleeping in workers for human wait — use `WAITING` + resume.

## Add a media provider

Media nodes wrap services (`ImageGenerationService`, `TTSService`, `video_pipeline`, `ChessVideoService`):

1. Add/extend the **domain service** + provider adapter (existing inference/media layout).
2. Keep provider-specific env/secrets in service/config — not workflow graphs.
3. Point the node at the service API; reuse job/asset models.
4. Support `mock_generation` via `testing_support.py` for dry-runs.
5. Document capability tags so compiler can gate accounts lacking media support.
6. Tests: node unit + optional engine dry-run.

Chess specifics: [chess-video.md](chess-video.md) — node must not call parse/render directly.

## Add a social provider

See [social-accounts.md](social-accounts.md). Workflow side only needs `social_account_id` + capability fingerprint.

## Configuration & snapshots

Use `ConfigResolver` layers — do not scatter merge rules inside nodes. Historical runs must not re-resolve live settings.

## Debugging checklist

See [workflow-engine.md](workflow-engine.md#debugging-failed-runs). Prefer run-detail I/O + correlation_id in logs.

## Testing expectations

| Change | Add |
|--------|-----|
| New node | registry + execute unit test |
| Compiler rule | `test_workflow_graph_compiler.py` |
| Engine behavior | engine / strategy tests |
| UI surface | page or feature vitest |
| Cross-cutting | update [workflows-phase18-testing.md](workflows-phase18-testing.md) matrix / regression manifest |

## Package layout

```text
backend/modules/workflows/
  models.py / run_models.py
  registry.py / compiler*.py / engine*.py
  config_*.py / security.py / observability.py
  nodes/
  router.py / automation_router.py
frontend/src/
  api/workflows.ts
  features/workflows/*
  pages/Workflow*.tsx AutomationsPage.tsx
```

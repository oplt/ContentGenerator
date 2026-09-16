# Phase 8 — Do Not Trust Client-Supplied Capability Context

## End state

* Runtime capability truth comes from `SocialAccount` (platform, flags, status).
* Clients may supply **account IDs + policy flags only** (`RuntimeClientContext`).
* Client-supplied `account_capabilities` / platform maps are rejected or stripped.
* Design-time hypothetical caps remain available via `/validate-graph` and
  explicit `/simulate-graph` (`DesignValidationContext`).
* `automation_id`, `brand_id`, and `social_account_ids` are tenant-authorized
  before run start / node test.

## Separation

| Type | Use |
|------|-----|
| `RuntimeClientContext` | Run start / node test request body |
| `build_runtime_compile_context` | Server builds authoritative `CompileContext` |
| `DesignValidationContext` | Editor what-if / simulate-graph |

## Files

* `graph_schema.py` — `RuntimeClientContext`, `DesignValidationContext`
* `capability_context.py` — `build_runtime_compile_context`, strip client maps
* `runtime_bindings.py` — `authorize_runtime_bindings`
* `engine.py` / `node_tester.py` / `router.py` (`/simulate-graph`)
* `schemas.py` — start-run / node-test use `RuntimeClientContext`

## Tests

```bash
cd backend && pytest -q tests/test_workflow_phase8_capability_trust.py \
  tests/test_workflow_platform_capabilities.py \
  tests/test_workflow_production_gaps.py -k 'runtime or capability or simulate'
```

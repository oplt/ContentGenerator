# Workflow Domain — Phase 2 (Node Contract + Registry)

Typed workflow nodes as adapters over existing domain services.

## Layout

```text
backend/modules/workflows/
  nodes/base.py          WorkflowNode contract, NodeResult
  nodes/*.py             Category packs (slice + stubs)
  registry.py            WorkflowNodeRegistry
  context.py             WorkflowNodeContext builder
  compiler.py            Minimal type/config validation (full DAG = Phase 3)
  engine.py              Linear in-process engine (Phase 5)
  service.py / router.py Node catalog API
```

## Implemented vertical slice

| Node | Wraps |
|------|--------|
| `manual_trigger` | Pass-through trigger payload |
| `generate_text` | `get_llm_provider().generate_text` |
| `approval` | `ApprovalService.send_for_approval` → `WAITING` |
| `publish` | `PublishingService.publish_now` (dry-run default) |

Other catalog entries are registered stubs (`WorkflowNodeNotImplementedError` on execute).

## API

* `GET /api/v1/workflows/nodes`
* `GET /api/v1/workflows/nodes/{node_type}`
* `POST /api/v1/workflows/nodes/{node_type}/validate-config`
* `POST /api/v1/workflows/validate-graph`

## Next

Phase 3 — full graph schema + compiler (edges, cycles, ports).

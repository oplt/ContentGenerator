# Phase 14 — Real Port-Based Canvas

Registry port metadata drives React Flow handles. Connections serialize into
`GraphEdge.source_port` / `target_port`. Backend compiler stays authoritative.

## Behavior

| Concern | Implementation |
|---------|----------------|
| Handles | One Handle per `input_ports` / `output_ports` (ids = port names) |
| Edge serialization | `sourceHandle` → `source_port`, `targetHandle` → `target_port` |
| Compatibility | Client `typesCompatible` mirrors `compiler_checks.types_compatible` |
| Rejection | `isValidConnection` blocks incompatible / unavailable / self links |
| Indicators | invalid (compile), unavailable, WAITING-capable, category glyph, run status |
| Ops | edge condition labels, Ctrl/Cmd+D duplicate, Delete/Backspace, fit, auto-layout |

Untyped nodes (empty ports) use a `__default__` handle and persist `null` ports.

## Files

* `features/workflows/portCompatibility.ts`
* `features/workflows/canvasGraph.ts` — adapters + indicators options
* `features/workflows/WorkflowCanvasNode.tsx` — multi-port handles
* `features/workflows/WorkflowCanvas.tsx` — validation + keyboard
* `api/workflowTypes.ts` — `source_port` / `target_port` on edges

## Non-goals

* n8n feature parity
* replacing backend compile validation
* full run-operator UI (Phase 15 wires `runStatuses` on inspection)

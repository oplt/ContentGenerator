# Workflow Domain — Phase 14 (Visual Canvas)

`@xyflow/react` editor over the same `WorkflowVersion.graph_json` as Phase 13.

## Layout

| Region | Content |
|--------|---------|
| Left | Node palette (by category) |
| Center | Canvas (zoom/pan, connect, delete, minimap) |
| Right | Selected node JSON config |
| Bottom | Validation errors |

Positions stored in `graph.metadata.layout` — backend graph schema unchanged.

## Canvas ops

* add from palette
* connect edges (approval → `approved` condition)
* drag / delete nodes+edges
* auto-layout (topo vertical)
* duplicate selected
* fit view
* validate / save draft / publish / test run (unchanged APIs)

## Non-goals

* full n8n feature parity
* schema-driven forms
* single-node test (Phase 15)

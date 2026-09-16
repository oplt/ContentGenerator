# Workflow Domain — Phase 14 (Port-Based Canvas)

`@xyflow/react` editor over `WorkflowVersion.graph_json` with registry ports.

## Layout

| Region | Content |
|--------|---------|
| Left | Node palette (by category) |
| Center | Port-handled canvas (zoom/pan, connect, delete, minimap) |
| Right | Schema-driven node config (Phase 13) |
| Bottom | Validation summary |

Positions stored in `graph.metadata.layout` — backend graph schema unchanged
(`source_port` / `target_port` already exist on `GraphEdge`).

## Canvas ops

* add from palette
* connect **named ports** (incompatible types rejected in UI)
* drag / delete nodes+edges
* auto-layout (topo vertical)
* duplicate selected (button or Ctrl/Cmd+D)
* fit view
* indicators: invalid / unavailable / waiting-capable / category / run status
* validate / save draft / publish / test run (unchanged APIs)

## Non-goals

* full n8n feature parity
* replacing compiler as source of truth

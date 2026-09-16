# Phase 12 — Node Implementation Availability

Registered nodes expose explicit executability. Do not infer from class names.

## Metadata

On every `WorkflowNode`:

* `implementation_status`: `stable` | `beta` | `unavailable`
* `is_executable()` → false when `unavailable`

Stubs from `make_stub_node(...)` set `unavailable`.

API (`GET /workflows/nodes`) returns:

* `implementation_status`
* `executable`

## Compiler

`validate_node_executability` emits:

```text
code: node_not_executable
```

when any resolved node is unavailable.

This runs on the same `WorkflowCompiler.validate_graph` path used by:

* publish
* run
* enabled automation schedule start

Draft save does **not** compile — drafts may still contain unavailable nodes.

## Implemented (Phase 12)

| Node | Status | Wraps |
|------|--------|-------|
| `research_sources` | stable | `SourceIngestionService.run_ingestion` |
| `fetch_metrics` | stable | `AnalyticsService.sync_snapshots` + `overview` |

Still unavailable (by design):

* `schedule_trigger` (automations use DB schedules today)

`webhook_trigger` is **stable** (Phase 17 signed automation ingress).

`generate_canonical_content` is marked **beta**.

## Frontend

* Palette: unavailable nodes show "Coming soon", disabled, not addable
* Step list: unavailable types omitted from Add dropdown
* Beta nodes labeled `(beta)`

## Engine

Defense in depth: unavailable nodes fail permanently with `node_not_executable`
if somehow scheduled.

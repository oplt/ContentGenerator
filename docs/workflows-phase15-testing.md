# Workflow Domain — Phase 15 (Testing / Dry Runs)

## Validation

`POST /workflows/validate-graph` — compile only, no external calls (unchanged).

## Dry-run start

`POST /workflows/definitions/{id}/runs` flags:

| Field | Effect |
|-------|--------|
| `dry_run` | Force publish `dry_run=true` via `run_config`; `trigger_type=dry_run` |
| `mock_generation` | Skip LLM/media providers; return deterministic mock outputs |
| `simulate_approval` | Auto-resume WAITING approval nodes as `approved` |

Account selection / compile context still real and tenant-scoped.

## Single-node test

`POST /workflows/nodes/{node_type}/test`

* Auth: `content:write`
* Publish forced dry-run when `dry_run=true`
* Approval returns simulated success (no channel send) when `dry_run=true`
* Optional `mock_generation` for AI/media nodes
* Response includes inputs / config / output / error

## UI

Editor: dry-run checkboxes + Test Run + Test node panel with I/O JSON.

Run detail: shows each node `input_json` / `output_json`.

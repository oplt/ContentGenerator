# Workflow Domain — Phase 3 (Graph Schema + Compiler)

Canonical DAG-as-data + validate-before-publish.

## Graph format

Stored on `WorkflowVersion.graph_json`:

```json
{
  "nodes": [{"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}}],
  "edges": [{"source": "trigger", "target": "generate", "condition": null}],
  "metadata": {}
}
```

Schema: `backend/modules/workflows/graph_schema.py`.

## Compiler checks

* duplicate node IDs
* unknown types / versions
* invalid config (Pydantic)
* dangling / self edges
* cycles
* unreachable nodes
* multiple triggers (unless allowed)
* trigger incoming edges
* incompatible ports
* approval after publish / not before publish
* missing publish targets (`CompileContext.social_account_ids`)
* account capability mismatches

## Publishing

Draft → validate → immutable `WorkflowVersion` (`published_at` + checksum).

Saving after publish creates a new draft version; published rows stay immutable.

## API additions

* `GET/POST /workflows/definitions`
* `GET /workflows/definitions/{id}`
* `GET /workflows/definitions/{id}/versions`
* `PUT /workflows/definitions/{id}/draft`
* `POST /workflows/definitions/{id}/publish`

## Next

Phase 4 — `WorkflowRun` / `WorkflowNodeRun` durable execution state.

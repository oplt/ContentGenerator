# Phase 3 — port/binding DAG data flow

Roadmap: `prompt.txt` Phase 3.

## Design

The engine resolves node inputs without node-type switches:

| schema_version | Resolver |
|----------------|----------|
| `1` (default for historical graphs) | `engine_inputs_legacy.py` — frozen aliases |
| `>= 2` (new publishes) | `engine_inputs_ports.py` — ports + bindings |

`engine_inputs.py` only dispatches on `schema_version`.

### Ports on edges

```text
source_output[source_port] → target_input[target_port]
```

### Input bindings

```json
{
  "input_bindings": {
    "prompt": {"source": "trigger", "path": "topic"},
    "system_hint": {"source": "constant", "value": "be brief"}
  }
}
```

Sources: `trigger`, `workflow_input`, `constant`, `context`, `node`.

Dotted `path` lookup only — no expression language.

### Output validation

After execute, `node.validate_output(...)` runs. Violations fail as
`invalid_node_output` / `permanent` (not retried).

### Publish stamping

`WorkflowVersioning.publish` sets `schema_version=2` on newly published graphs.
Already-published versions are never rewritten.

## Files

- `graph_schema.py` — `schema_version`, `InputBinding`, `GraphNode.input_bindings`
- `engine_inputs.py` — facade
- `engine_inputs_ports.py` — v2 resolver
- `engine_inputs_legacy.py` — v1 only
- `engine_inputs_bag.py` — shared merge/lookup
- `compiler_checks.validate_input_bindings`
- `engine_execute.py` — passes graph/ports; validates outputs
- Tests: `test_workflow_port_bindings.py`

## Acceptance

- Adding a node does not require editing `engine_inputs.py`
- Facade has zero `if node_type == "..."` branches
- Historical graphs remain executable via schema_version 1

## Next phase

**Phase 5 — Make wait / delay actually durable**

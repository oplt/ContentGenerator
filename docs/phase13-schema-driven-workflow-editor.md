# Phase 13 — Schema-Driven Workflow Editor

Normal node configuration is form-based from registry `config_schema`.
Advanced JSON remains available as an escape hatch.

## Components

| Component | Role |
|-----------|------|
| `WorkflowNodeConfigForm` | RHF form from `config_schema` |
| `WorkflowFieldRenderer` | string / textarea / int / number / bool / enum / string[] / JSON fallback |
| `WorkflowPortHandle` | inspector port chips (canvas Handles in Phase 14) |
| `WorkflowValidationPanel` | graph validation summary |

## Behavior

* Palette add seeds `config` from schema defaults
* Form edits debounce `POST /workflows/nodes/{type}/validate-config`
* Field-level errors mapped from backend messages when possible
* Unsupported nested objects use a JSON textarea for that field
* Toggle **Advanced JSON** for full raw config editing

## Types

`WorkflowNodeDefinition` includes `input_schema`, `output_schema`, `input_ports`,
`output_ports` (already returned by the backend registry).

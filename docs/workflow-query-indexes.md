# Workflow query indexes (ops Phase 5)

## Access patterns → indexes

| Query | Index |
|-------|--------|
| Definitions list `tenant_id` + alive `ORDER BY updated_at DESC` | `ix_workflow_definitions_tenant_updated_at_alive` partial `deleted_at IS NULL` |
| Automations list `tenant_id` + alive `ORDER BY updated_at DESC` | `ix_automations_tenant_updated_at_alive` partial `deleted_at IS NULL` |
| Scheduler due claim `enabled` + `schedule` + `next_run_at <= now()` | `ix_automations_due_schedule_next_run_at` partial on due schedule rows |
| Runs list `tenant_id ORDER BY created_at DESC LIMIT n` | `ix_workflow_runs_tenant_id_created_at` |

## Removed (redundant / misaligned)

* `ix_workflow_definitions_tenant_id_enabled` — `(tenant_id, deleted_at)` alive-only; superseded by updated_at list index
* `ix_automations_enabled_next_run_at` — lacked `trigger_type='schedule'`; superseded by due-schedule partial

## Migration

`a3b4c5d6e7f8_workflow_query_indexes` (revises `f2a3b4c5d6e7`)

```bash
make migrate
```

## EXPLAIN notes

On empty/tiny tables Postgres may still seq-scan definitions; with `enable_seqscan=off` the new index is chosen. Automations list, scheduler, and runs list pick the new indexes without an explicit sort step for the ORDER BY columns.

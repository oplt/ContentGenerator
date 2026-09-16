# Phase 6 — automation / brand / account integrity

Roadmap: `prompt.txt` Phase 6.

## Rules

### Brand ↔ account (strict)

Automation targets must be linked through `BrandSocialAccount`
(`enabled`, `deleted_at IS NULL`) for the automation's `brand_id`.

Override (explicit only): `allow_unlinked_targets=true` on create/update.
Default remains strict.

### Brand validation

Create/update verifies brand:

* exists
* same tenant
* not soft-deleted

### Definition ↔ version

Service checks `workflow_version.workflow_definition_id` matches the automation
definition. DB enforces via:

```text
uq_workflow_versions (tenant_id, workflow_definition_id, id)

automations
  (tenant_id, workflow_definition_id, workflow_version_id)
  → workflow_versions
```

### current_version

```text
workflow_definitions
  (tenant_id, id, current_version_id)
  → workflow_versions (tenant_id, workflow_definition_id, id)
```

Prevents pointing `current_version_id` at another definition/tenant.

## Files

- `automation_integrity.py`
- `automation_service.py` / `automation_schemas.py`
- Alembic `f8a9b0c1d2e3`
- Tests: `test_workflow_phase6_automation_integrity.py`

## Next phase

**Phase 7 — Harden scheduler lifecycle**

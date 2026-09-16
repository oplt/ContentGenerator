# Workflow Domain — Phase 1 (Domain Foundation)

Minimum durable model for multi-brand, multi-account reusable automations.

## Reused

| Concept | Location |
|---------|----------|
| Brand / BrandProfile | `backend/modules/content_strategy/models.py` |
| SocialAccount | `backend/modules/publishing/models.py` |
| Mixins / registry | `backend/db/base.py`, `backend/db/model_registry.py` |

## Added

| Table | Purpose |
|-------|---------|
| `brand_social_accounts` | Brand ↔ SocialAccount M2M + per-link overrides |
| `workflow_definitions` | Reusable workflow shell (`draft` / `active` / `archived`) |
| `workflow_versions` | Immutable graph snapshots (`version` int; not ORM VersionMixin) |
| `automations` | Bind workflow version + brand + trigger |
| `automation_targets` | Per-automation destination accounts |

Composite `(tenant_id, parent_id)` foreign keys prevent cross-tenant references.

## Migration

`d0e1f2a3b4c5_workflow_domain_foundation` (reversible). Also adds
`uq_brands_tenant_id_id` and `uq_social_accounts_tenant_id_id` for composite FKs.

## Out of scope (later phases)

Node registry, compiler, WorkflowRun, engine, APIs, UI.

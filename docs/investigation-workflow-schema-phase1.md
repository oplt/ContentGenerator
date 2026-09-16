# Phase 1 investigation — workflow schema missing

**Date:** 2026-09-16  
**Status:** Root cause confirmed (no schema repair in this note — see Phase 2).

## Confirmed root cause

**Primary: B — migrations exist but were not applied.**

Live DB `content` (from `DATABASE_URL`):

| Check | Result |
|-------|--------|
| `alembic_version` | `c9d0e1f2a3b4` (chess board_theme) |
| Alembic head | `f2a3b4c5d6e7` |
| Workflow tables present | **none** |

Pending revisions (not applied):

1. `d0e1f2a3b4c5` — `brand_social_accounts`, `workflow_definitions`, `workflow_versions`, `automations`, `automation_targets`
2. `e1f2a3b4c5d6` — `workflow_runs`, `workflow_node_runs`
3. `f2a3b4c5d6e7` — `automation_occurrences`

That matches `UndefinedTableError` for `workflow_definitions` / `automations` / `workflow_runs` and Celery `tick_due_automations_task` crashes.

**Secondary: G — no startup/deploy gate runs `alembic upgrade head` before API/workers.**  
Compose starts Postgres/Redis/Celery/API without a migrate step; README documents manual `alembic upgrade head` only.

## Ruled out

| Code | Why not |
|------|---------|
| A | Workflow migrations exist under `backend/alembic/versions/` |
| C | `alembic/env.py` sets `target_metadata = Base.metadata`; `model_registry` imports `workflows.models` (re-exports `run_models`) |
| D | App `.env` `DATABASE_URL` → `content@localhost/content`; inspected DB is that DB (compose default name `content_generator` unused by this app URL) |
| E | `search_path` = `"$user", public`; tables queried in `public` |
| F | Single head `f2a3b4c5d6e7` |

## ORM workflow tables (8)

`brand_social_accounts`, `workflow_definitions`, `workflow_versions`, `automations`, `automation_targets`, `automation_occurrences`, `workflow_runs`, `workflow_node_runs`

PG has **0** of these; ORM metadata has all **8**.

## Key locations

| Item | Path |
|------|------|
| Base / metadata | `backend/db/base.py`, `backend/alembic/env.py` |
| Models | `backend/modules/workflows/models.py`, `run_models.py` |
| Brand link | `backend/modules/content_strategy/models.py` → `brand_social_accounts` |
| Registry import | `backend/db/model_registry.py` |
| Migrations | `d0e1…`, `e1f2…`, `f2a3…` |
| Celery beat tick | `backend/workers/…` → `tick_due_automations_task` |

## Next (Phase 2)

Apply pending heads on the existing `content` DB (`alembic upgrade head`) — do **not** use `create_all()` at startup; do **not** wipe data. Validate empty-DB + upgrade-from-`c9d0e1f2a3b4` paths.

## Phase 2 applied

* `alembic upgrade head` on live `content`: `c9d0e1f2a3b4` → `f2a3b4c5d6e7`
* All 8 workflow tables created; existing brand/tenant/account rows preserved
* Existing migrations matched ORM — no new revision required

## Phase 3

Drift gate documented in [`schema-drift-protection.md`](schema-drift-protection.md).

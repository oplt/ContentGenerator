# Schema drift protection (Phase 3)

## Problem

Workflow code shipped while Postgres stayed at `c9d0e1f2a3b4`, causing
`UndefinedTableError` storms on API + Celery (`tick_due_automations_task`).

## Design

```text
make migrate / alembic upgrade head
        ↓
API lifespan assert_schema_at_head
Celery worker/beat init assert_schema_at_head
        ↓
/health/ready includes migrations check → HTTP 503 if behind
```

## Components

| Piece | Behavior |
|-------|----------|
| `backend/db/schema_revision.py` | Compare `alembic_version` vs script heads |
| `SCHEMA_REVISION_ENFORCE` | Default `true`; set `false` only for break-glass |
| `/api/v1/health/ready` | `checks.migrations`; **503** when db/migrations fail |
| API lifespan | Raises `RuntimeError` on drift (process fails closed) |
| Celery `celeryd_init` / `beat_init` / worker process init | Raise → worker/beat do not run tasks |
| `make migrate` | `alembic upgrade head` |
| `Makefile.local` / `Procfile.dev` | Migrate before API/worker/beat; browser waits on `/ready` |

## Local commands

```bash
make migrate
make local-dev
```

## Tests

* `tests/test_schema_revision.py`
* `tests/test_phase4_health.py` (concurrent ready + 503 on drift)

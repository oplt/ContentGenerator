# Phase 0 — baseline, repository hygiene, regression safety

Roadmap source: `prompt.txt` (production workflow hardening). This phase does **not**
change workflow engine behavior.

## 0.1 Repository hygiene

- Removed tracked runtime files under `logs/` from git (kept locally, ignored).
- `.gitignore`: `logs/`, `*.log` (plus existing `backend/logs/`).
- CI `repo-hygiene` and `make quality-gates` reject tracked `^logs/` and `.log$`
  paths (optional whitelist for deliberate fixtures).
- `backend/core/logging.py` writes to repo-root `logs/` via path relative to the
  package (no machine-specific absolute path).

## 0.2 Verification results (2026-09-16)

| Check | Result |
|-------|--------|
| Ruff | **Pass** |
| Mypy | **Fail** — 52 errors across 24 files (pre-existing; chess_video, workflows, health_ready, etc.) |
| `pytest -m "not integration"` | **Fail** — 4 failures: line budget (8 files), phase4 HTTP semaphore spy, chess_video router commit, phase3 path (fixed) |
| `tests/test_workflow_*.py` | **Pass** (gap suite xfail as expected) |
| `pytest -m integration tests/test_migration_drift.py` | **Pass** (4 tests incl. workflow downgrade/upgrade roundtrip) with project `DATABASE_URL` |
| Frontend `npm run lint` | **Fail** — 10 ESLint errors (React hooks / refresh rules) |
| Frontend Vitest / build | Not run (blocked by lint in `make check`) |

Alembic roundtrip added: `test_alembic_workflow_migrations_downgrade_and_upgrade` downgrades to
`c9d0e1f2a3b4`, then upgrades to head on disposable Postgres.

## 0.2 Verification commands

Run locally before Phase 1:

```bash
make check
make regression-unit
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/test_workflow_*.py
cd frontend && npm test -- --run && npm run build
cd frontend && npx playwright test --project=chromium --project=mobile-chrome  # when stack/API available
```

Alembic on disposable Postgres:

```bash
export CG_RUN_DB_MIGRATIONS=1 DB_POOL_USE_NULL=true DATABASE_URL=postgresql+asyncpg://...
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q -m integration tests/test_migration_drift.py
```

## 0.3 Gap regression suite

`backend/tests/test_workflow_production_gaps.py` — `workflow_production_gap` tests
marked `xfail(strict=True)` for Phase 1–3 gaps (claims, one-node Celery task,
recovery, TaskExecution linkage, retry fields, port-based inputs). Remove `xfail`
when each phase closes the gap.

## Gaps confirmed (pre–Phase 1)

| Area | Current state |
|------|----------------|
| Node claims | No claim lease columns or `claim_ready_node` repository API |
| Execution | `WorkflowEngine.advance()` loops `execute_ready_node` inline (API/worker) |
| Celery | `advance_workflow_run_task` runs full advance, no `execute_workflow_node_task` |
| Telemetry | `task_execution_id` on `WorkflowNodeRun` not set during execution |
| Recovery | No periodic stale RUNNING node recovery task |
| Input routing | `engine_inputs.py` uses node-type-specific branches |

## Next phase

**Phase 1** — durable node execution, atomic claiming, one-node worker task, crash recovery.

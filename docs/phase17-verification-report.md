# Phase 17 — live verification report

Date: 2026-09-16  
Stack: local API on `:8000`, PostgreSQL at head `a3b4c5d6e7f8`, Redis ok (ready check).

Re-run:

```bash
PYTHONPATH=. backend/.venv/bin/python backend/scripts/verify_phase17.py
```

## Schema / UndefinedTableError

| Check | Result |
|---|---|
| Alembic revision | **At head** (`a3b4c5d6e7f8`) |
| `workflow_definitions` … `workflow_node_runs` | **All present** in live DB |
| Workflow GET after migrate | **HTTP 200** (empty lists) — no 500 |

Historical `UndefinedTableError` entries in `logs/app_2026-09-16.log` (~07:15 UTC) predate
the workflow-domain migration; **no recurrence** after head upgrade (verified 08:26 UTC).

## Workflow HTTP (demo tenant)

Authenticated via `POST /api/v1/auth/sign-in` (demo seed):

| Endpoint | Status | Notes |
|---|---|---|
| `GET /api/v1/workflows/definitions` | **200** | `[]` |
| `GET /api/v1/workflows/automations` | **200** | `[]` |
| `GET /api/v1/workflows/runs` | **200** | `[]` |

Request logs show real correlation IDs (not `n/a`) and tenant UUID on success paths.

## Automation scheduler

Three in-process `AutomationScheduler.tick()` cycles completed with **no exception**
(0 due automations claimed — expected on empty tenant).

Concurrent double-claim behavior remains covered by unit/integration tests
(`test_workflow_scheduler.py`, `test_workflow_scheduler_pg.py`).

## Correlation / tenant on errors

| Check | Result |
|---|---|
| `X-Correlation-ID` on 401 JSON | Echoed in `error.correlation_id` |
| Success workflow GET logs | `correlation_id` + `tenant_id` populated |
| Exception-path tenant retention | Covered by `test_tenant_context_on_errors.py` |

## Frontend duplicate traffic

Not re-measured in-browser this pass. Mitigations in place:

- TanStack Query `staleTime` (moderate = 5 min) via `queryClient.ts`
- `shouldRetryQuery` skips 400/401/403 (`queryRetry.test.ts`)
- Content tabs mount-on-active (phase 8)

Manual spot-check recommended on Dashboard navigation if FE is running.

## Ingestion before/after benchmark

**No new paired before/after run** in this verification session (prompt requires
measurements to claim improvement).

Existing evidence:

- **Phase 11/13 architecture:** clustering LLM moved **after** persist commit;
  stage timings on `fetch_run.metadata.stage_timings_ms` when profiler enabled.
- Recent successful fetch runs had **0 new articles** — stage metadata empty/null.
- Historical sample in `prompt.txt` (9–67 s ingest) predates TX split; re-benchmark
  with a source that ingests ≥1 new article and compare `stage_timings_ms` +
  `cg.llm.call.duration_ms` metrics.

Suggested capture:

```bash
# After ingest with new articles:
# inspect fetch_run.metadata.stage_timings_ms and worker task_id on result
```

## Phase 17 exit criteria

| Criterion | Status |
|---|---|
| No workflow table missing errors on current DB | **Pass** |
| Workflow list endpoints valid (not 500) | **Pass** |
| Scheduler multi-cycle without crash | **Pass** |
| Real correlation ID in logs/responses | **Pass** |
| Ingestion performance delta quantified | **Not claimed** (needs instrumented A/B) |

## Required final report (ops Phases 1–17 summary)

### 1. Confirmed root causes

- Missing workflow-domain tables / stale DB revision → `UndefinedTableError` on workflow routes.
- Correlation middleware ordering → `correlation_id: n/a` in logs.
- Missing `briefs:write` on default roles → duplicate 403 on `POST /briefs`.
- Audit log strict payload typing → HTTP 400 on mixed JSON values.
- Ingestion held DB sessions across fetch/LLM → pool pressure and long TX.
- Celery result omitted pre-assigned `task_id` on success.
- Social accounts ~185 ms was a **single outlier**, not sustained handler slowness.

### 2. Files modified (representative)

- Migrations: workflow domain, query indexes, schema revision gate.
- Backend: ingestion split-phase, `cluster_enrichment`, task traceability, observability middleware, enrichment cache, publishing serializers/profiling.
- Frontend: query retry policy, briefs RBAC, API client dedupe.
- Tests/docs: phases 13–16 regression matrix, Phase 17 verify script.

### 3. Migrations created or repaired

- Workflow foundation (`d0e1f2a3b4c5` … `a3b4c5d6e7f8`) — definitions, automations, runs, occurrences, indexes.
- `make migrate` / `alembic upgrade head` required before workflow APIs.

### 4. Automated verification

- `make regression-unit` + frontend `npm test -- --run`
- `CG_RUN_DB_MIGRATIONS=1` integration migration tests
- `backend/scripts/verify_phase17.py` for live stack smoke

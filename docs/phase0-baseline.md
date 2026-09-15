# Phase 0 baseline — 2026-09-15

## Scope

Baseline captured before changing production behavior for the concurrency and
latency issues described in `bugs.txt`. Existing uncommitted changes were
preserved.

## Runtime architecture

```text
React/Vite frontend
  -> typed fetch clients / TanStack Query / auth context
  -> FastAPI app (/api/v1)
  -> module routers -> services -> repositories
  -> PostgreSQL (SQLAlchemy async engine/sessionmaker)
  -> Redis (cache + Celery broker/result backend)

Celery Beat (5 schedules)
  -> Redis broker
  -> gevent worker (Procfile.dev: concurrency=16)
  -> synchronous task wrappers
  -> shared asyncio event loop (backend/workers/runtime.py)
  -> async DB/HTTP/Redis/provider work
```

### Relevant configuration

- Celery broker/result backend: `redis://localhost:6379/0`.
- Beat schedules: source polling every 5 minutes, tenant rescoring and stale
  approval expiry every 30 minutes, publishing every minute, and a daily
  trending-repository fan-out.
- Development worker: gevent pool, concurrency 16, all workload queues in one
  process.
- Worker pool settings intended by application configuration: DB pool size 2,
  overflow 2; IO concurrency 4; LLM 2; media 1; publishing 2; DB 2.
- API defaults remain DB pool size 5, overflow 10.
- `AsyncSession` is created from a process-global async engine/sessionmaker;
  HTTP uses a process-scoped `httpx.AsyncClient`; Redis uses shared async
  clients.

## Reproduction and measurements

| Check | Baseline result |
|---|---|
| Worker event-loop concurrency | Reproduced: 3 concurrent calls to `_run_on_worker_loop` yielded 2 `ok` results, 1 `RuntimeError: This event loop is already running`, and `RuntimeWarning: coroutine 'operation' was never awaited`. |
| `/api/v1/health/live` | Unavailable: connection refused; no API process was running. |
| `/api/v1/health/ready` | Unavailable: connection refused; no API process was running. |
| `/api/v1/health/metrics` | Unavailable: connection refused; no API process was running. |
| Celery task failures / worker event-loop logs | No worker process was running, so no live task log sample was available. Static inspection confirms the unsafe shared loop path affects `poll_sources_task`, `rescore_all_tenants_task`, and `publish_due_jobs_task` through `run_async_task`. |
| Frontend duplicate auth refresh | Static inspection found a module-level `refreshPromise` single-flight guard in `frontend/src/api/client.ts`; runtime traffic could not be measured because the frontend was not running. |
| Frontend duplicate GETs | Static inventory: 54 `useQuery` calls and 3 direct `apiFetch` call sites. Runtime traffic could not be measured because the frontend was not running. |
| Web Vitals traffic | `initWebVitals()` is called once from `main.tsx`; runtime request count could not be measured because the frontend was not running. |
| Cluster detail 422 / audit logs 400 | No live API was available; no request samples were captured. Relevant routes are present at `/api/v1/stories/clusters/{cluster_id}` and `/api/v1/audit`. |
| Source-ingestion / dashboard latency | Not measurable without a running API and backing services. |
| Worker concurrency / DB pool / CPU / RAM | No worker/API/database processes were running. Configured worker command is gevent concurrency 16; configured worker DB pool ceiling is 4 connections. |

## Baseline test result

Command:

```text
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q \
  tests/test_celery_policy.py tests/test_db_pooling.py \
  tests/test_phase14_worker_capacity.py tests/test_phase15_observability.py \
  tests/test_app_smoke.py
```

Result: 30 passed, 2 failed.

Both failures are `tests/test_app_smoke.py` and occur during app import because
the existing chess-video router imports `get_db` from `backend.db.session`,
while the dependency currently lives in `backend.api.deps.db`. This is an
existing startup blocker independent of the Phase 0 asyncio reproduction.

## Root causes established in Phase 0

1. Celery gevent tasks can enter the same process-global asyncio event loop at
   the same time; `run_until_complete()` is not concurrency-safe.
2. The current worker process was not running during measurement, preventing
   live latency, traffic, resource, and queue observations.
3. The current application import baseline is broken by the chess-video
   router's incorrect `get_db` import.

## Files changed for Phase 0

- `docs/phase0-baseline.md` — this baseline and architecture report.


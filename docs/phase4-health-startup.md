# Phase 4 — health checks, metrics, and startup reliability

## Root causes

- `/health/ready` checked DB, Redis, and inference providers serially. Each
  provider used the general HTTP retry/timeout policy, so unavailable optional
  providers could add seconds of latency.
- Readiness performed a second database operation to load worker status after
  the dependency check.
- The application exposed JSON metrics at `/api/v1/health/metrics`, while
  root-path scrapers requesting `/metrics` received 404. No in-repository
  frontend caller for `/metrics` was found.
- The browser process waited only for Vite, so it could open before FastAPI was
  accepting requests.

## Changes

- DB, Redis, and inference readiness checks now run concurrently.
- Each dependency check has a bounded timeout controlled by
  `HEALTH_CHECK_TIMEOUT_SECONDS` (default 750ms).
- Inference providers are checked concurrently with the same timeout and
  provider retries cannot extend the readiness deadline.
- Only the configured `LLM_PROVIDER` is required for readiness; optional
  provider failures are reported in `components.inference.providers` without
  degrading the overall inference check.
- Readiness now returns `components` and `timings_ms` with per-component
  latency, while retaining the existing response fields.
- Added a root `/metrics` compatibility endpoint backed by the existing metrics
  response; `/api/v1/health/metrics` remains unchanged.
- Browser startup now polls `/api/v1/health/live` and the Vite URL with bounded
  retry intervals before opening the browser. No fixed startup sleep was added.

## Before / after

| Check | Before | After |
|---|---|---|
| Readiness dependency execution | Serial DB → Redis → providers → second DB query | Concurrent bounded checks; worker status shares the DB check session |
| Optional provider failure | Could make inference readiness fail | Reported but does not fail readiness when configured provider is healthy |
| Component timings | Not exposed | `components[*].latency_ms` and `timings_ms` |
| Root `/metrics` | 404 | JSON metrics response |
| Browser startup | Waited for frontend only | Waits for backend liveness and frontend availability |

The readiness unit test uses three 30ms dependency checks and verifies total
execution stays below 150ms, demonstrating concurrent rather than serial
behavior. Live endpoint latency and startup noise could not be measured because
local services are not running.

## Validation

- Ruff checks for all changed Python files: passed.
- Phase 4 readiness test: passed.
- API import/OpenAPI smoke tests: 2 passed.
- Combined health/HTTP test invocation was stopped after it became non-reporting;
  the independently run Phase 4 tests passed.

## Files changed in Phase 4

- `backend/core/config.py`
- `backend/modules/inference/factory.py`
- `backend/api/v1/health.py`
- `backend/api/main.py`
- `Procfile.dev`
- `backend/tests/test_phase4_health.py`
- `docs/phase4-health-startup.md`


# Phase 1 — Celery / asyncio concurrency fix

## Root cause

Celery's gevent worker could enter the process-global `_worker_loop` from
multiple greenlets at the same time. Each invocation called
`loop.run_until_complete(...)`; the second invocation therefore hit
`RuntimeError: This event loop is already running`, and its coroutine was left
un-awaited.

## Fix

- `backend/workers/runtime.py` now owns one dedicated asyncio thread per worker
  process.
- Synchronous Celery wrappers submit awaitables through a thread-safe queue to
  that loop and wait on a `concurrent.futures.Future`.
- The loop is the single owner of async SQLAlchemy, HTTP, Redis, and provider
  operations created during task execution, avoiding cross-loop resource use.
- Worker shutdown submits cleanup to the same loop, then drains and joins the
  thread. No worker shutdown path calls `run_until_complete`.
- Redis cleanup was added to the worker shutdown lifecycle alongside the
  existing HTTP and database cleanup.

## Before / after

The Phase 0 reproduction launched three concurrent calls to the worker bridge:

- Before: 2 successful calls, 1 `RuntimeError: This event loop is already
  running`, and 1 `RuntimeWarning` for an un-awaited coroutine.
- After: 3 successful calls; no event-loop, un-awaited-coroutine, pending-task,
  or closed-loop errors were emitted.

## Regression coverage

Added `backend/tests/test_worker_runtime.py`, which runs three async-backed
operations concurrently and always shuts down the dedicated worker loop.

Validation:

```text
backend/.venv/bin/ruff check workers/runtime.py workers/signals.py tests/test_worker_runtime.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/pytest -q \
  tests/test_worker_runtime.py tests/test_db_pooling.py \
  tests/test_celery_policy.py tests/test_worker_recovery.py
```

Result: 24 passed. Live Celery/Redis validation was not possible because the
development services were not running.

## Files changed in Phase 1

- `backend/workers/runtime.py`
- `backend/workers/signals.py`
- `backend/tests/test_worker_runtime.py`
- `docs/phase1-celery-asyncio-fix.md`


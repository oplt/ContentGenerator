# Duplicate exception logging (ops Phase 10)

## Problem

The same failure was logged multiple times:

1. FastAPI `unhandled_exception` handler (`logger.exception`)
2. `RequestLoggingMiddleware` `request_failed` (`logger.exception`) when
   `BaseHTTPMiddleware` re-raised
3. Uvicorn `Exception in ASGI application`
4. Celery `celery.app.trace` on task failures

Clients sometimes also saw internal detail (SQL / validation dumps) via the
`ValueError` handler catching Pydantic `ValidationError`.

## Design

Canonical event: **`application_error`** (`backend/core/app_errors.py`)

Fields: `correlation_id` / `request_id`, `tenant_id`, `method`, `route`, `path`,
`status_code`, `error_type`, `error_code`, `duration_ms` (optional), sanitized
`error_message`, and **one** traceback when useful.

Per-request flag `request.state.app_error_logged` skips duplicate emits.

| Layer | Behavior |
|---|---|
| Exception handlers | Log once via `log_application_error` |
| Request middleware | Log only if not already logged; never second traceback |
| Client JSON | Opaque `internal_error` + correlation/request id |
| IntegrityError | 409, no SQL/`params` in response |
| Pydantic `ValidationError` | 500 internal (not 400) |
| Uvicorn / Celery trace | Filters drop duplicate ASGI/task trace lines |
| Celery `task_failure` | Structured `application_error` with `task_id` |

## Tests

`backend/tests/test_duplicate_exception_logging.py`

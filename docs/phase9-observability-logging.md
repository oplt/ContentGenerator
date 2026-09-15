# Phase 9 — Observability and logging cleanup

## Root cause

The application had correlation middleware, but it only read `X-Correlation-ID`; callers using the requested `X-Request-ID` contract were ignored. Middleware ordering also allowed request logging to observe `n/a` before the correlation middleware initialized request state. Standard-library loggers were not enriched from the structlog context, and repeated logging setup could attach duplicate handlers.

## Changes

- Accept a safe, bounded incoming `X-Request-ID` (with `X-Correlation-ID` retained for compatibility), or generate a UUID.
- Return both request/correlation headers and clear async log context after each request.
- Order middleware so request logging sees the established correlation ID.
- Add correlation IDs to standard-library log records through a logging filter.
- Make logging setup idempotent and disable duplicate Uvicorn access records; the structured request logger remains the application request record.
- Propagate correlation context through the shared outbound HTTP client.
- Propagate the originating request correlation ID into manually queued source-ingestion Celery tasks.
- Keep metrics, health, and Web Vitals success requests in domain metrics while suppressing their routine request log lines; failures remain logged.

## Validation

Regression tests cover safe request-ID handling, stdlib log enrichment, outbound HTTP propagation, and existing HTTP retry behavior. Focused Ruff and pytest checks passed.

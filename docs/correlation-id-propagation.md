# Correlation-ID propagation (ops Phase 6)

## Bug

`RequestLoggingMiddleware` was registered **outside** `CorrelationIdMiddleware`, so
`request.state.correlation_id` was still unset when logging captured it → `"n/a"`.
`CorrelationIdMiddleware` also cleared structlog contextvars in `finally` before the
outer logger wrote `request_complete`.

## Fix

Middleware order (outer → inner):

```text
CORS → CorrelationId → RequestLogging → app
```

(`add_middleware` is reverse-order: add logging first, then correlation, then CORS.)

Request logging reads `correlation_id` **after** `call_next` from `request.state`.
Exception logs use `correlation_id=` (same ID as response headers / error payload).
Error JSON exposes both `correlation_id` and `request_id` as the same value.

## Headers

Incoming (honored when safe): `X-Correlation-ID` or `X-Request-ID`  
Outgoing: both set to the same ID.

## Related

Tenant ID on exception paths: `docs/tenant-context-on-errors.md` (ops Phase 7).

## Tests

`backend/tests/test_correlation_id_propagation.py`

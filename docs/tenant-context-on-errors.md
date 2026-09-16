# Tenant context on errors (ops Phase 7)

## Bug

Membership resolution set `request.state.tenant_id` and structlog `tenant_id`, but failed
requests still logged `tenant_id: null`.

Causes:

1. `BaseHTTPMiddleware` often does not surface `request.state` mutations made inside the
   app to the outer logging middleware after `call_next`.
2. `CorrelationIdMiddleware` called `structlog.contextvars.clear_contextvars()`, wiping
   the structlog tenant bind with no independent fallback.

## Fix

`backend/core/request_context.py` holds per-request `correlation_id` and `tenant_id` in
`contextvars` (not process globals).

* `get_current_membership` → `set_tenant_id(...)` + `request.state.tenant_id`
* Request / exception logs read `request.state` first, then `get_tenant_id()`
* Error JSON includes `tenant_id` when known
* Correlation middleware clears request context only in `finally` (after inner logging)

## Tests

`backend/tests/test_tenant_context_on_errors.py` — membership resolves, repository raises,
structured error + request logs still carry the tenant UUID.

# Audit logs HTTP 400 (ops Phase 9)

## Cause

`GET /api/v1/audit/logs?limit=50` authenticated and tenant-scoped correctly, then failed while
building `AuditLogResponse`:

* schema declared `payload: dict[str, str]`
* writers store mixed JSON (`bool`, `int`, nested objects)
* `AuditLogResponse.model_validate(...)` raised Pydantic `ValidationError`
* `ValidationError` subclasses `ValueError`, caught by the global handler → **HTTP 400**

Not a missing query param / pagination / FE caller bug. Limit=50 was already correct.

## Fix

Align response schema with the ORM / writers: `payload: dict[str, Any]`.
Frontend `AuditLog.payload` → `Record<string, unknown>`.

## Tests

`backend/tests/test_audit_logs_http.py` — page-shaped `?limit=50` with mixed payload → 200.

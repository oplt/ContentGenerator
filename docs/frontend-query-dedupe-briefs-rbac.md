# Frontend query dedupe + briefs RBAC (ops Phase 8)

## Duplicate requests

Server state uses TanStack Query with shared `queryKeys` / `queryKeyFactories`,
`queryPolicy` staleTimes, and Content tabs that mount only the active panel.

Default `staleTime` is moderate (5 min). Mutations never auto-retry.

## Retry policy

`lib/queryRetry.ts` + `ApiRequestError.retryable`:

* Retry: network, timeout, HTTP 429 / 502 / 503 / 504 (bounded)
* Never retry: 400 / 401 / 403 / 404 / other 4xx (except 429), plain 500, aborted
* Never auto-retry mutations (non-idempotent POST included)

Session refresh on 401 remains a single shared `refreshSession` (auth recovery, not
failure retry).

## POST `/api/v1/briefs` → 403

**Verdict B (partial):** route correctly requires `briefs:write`, but that code was
missing from `DEFAULT_PERMISSIONS` / system roles → every membership failed the check.

**Fix:** add `briefs:write` to system permissions; grant owner + editor. UI gates
generate/actions via `canWriteBriefs` and surfaces permission errors.

## Tests

* `frontend/src/lib/queryRetry.test.ts`
* `frontend/src/features/auth/access.test.ts`
* `backend/tests/test_briefs_write_permission.py`

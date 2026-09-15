# Phase 5 — API contract and backend correctness

## Findings

The cluster model and every cluster foreign key use PostgreSQL UUIDs. The list
and detail responses also declare `id: UUID`, and the frontend uses that same
`cluster.id` for links and detail requests. No legacy ObjectId column, mapping,
fixture, or migration exists for the reported 24-character value. It is
therefore a stale/foreign identifier, not a supported application identifier.

Audit logs already support an unfiltered tenant-scoped page with a safe default
`limit=50`; the backend route does not require a date range or pagination
cursor. The frontend was made explicit about that default to avoid relying on
an undocumented request shape.

## Changes

- Added strict canonical UUID validation to the frontend story-detail boundary.
  Invalid stale links are redirected to the story list and do not issue a
  malformed detail request.
- Added the same validation to the story API client for non-route callers.
- Made audit requests send `?limit=50` explicitly while preserving the backend
  default and tenant authorization.
- Added backend and frontend regression tests.

## Before / after

| Request | Before | After |
|---|---|---|
| Stale 24-character cluster link | Sent to FastAPI and returned 422 | Redirected locally; no malformed API request |
| Canonical UUID cluster link | Detail request succeeds | Unchanged |
| Audit page request | `/audit/logs` | `/audit/logs?limit=50` |
| Audit scope | Tenant dependency | Unchanged and still enforced |

## Validation

- Added `backend/tests/test_phase5_contracts.py` and ran it with API smoke and
  route-parity tests: 9 passed.
- Added `frontend/src/api/stories.test.ts`: 1 Vitest test passed.
- ESLint passed for all changed frontend files.
- `git diff --check` passed.

## Files changed in Phase 5

- `frontend/src/api/stories.ts`
- `frontend/src/pages/StoryDetailPage.tsx`
- `frontend/src/api/settings.ts`
- `frontend/src/api/stories.test.ts`
- `backend/tests/test_phase5_contracts.py`
- `docs/phase5-api-contracts.md`

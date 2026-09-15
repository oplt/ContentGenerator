# Phase 6 — Frontend network deduplication

## Root cause

React StrictMode intentionally mounts effects twice in development. The auth provider called `refresh()` directly, while the fetch client had a separate single-flight promise only for 401 retries. Concurrent auth bootstrap and retry callers could therefore create multiple `/auth/refresh` requests. Web Vitals initialization also had no module-level guard.

The dashboard and feature screens already use TanStack Query with tenant-scoped keys. Content tabs mount only their active panel, and source health/articles already have stable keys, so no duplicate effect-based fetch path was found there. The source query functions did not, however, forward TanStack Query cancellation signals.

## Changes

- `frontend/src/api/client.ts`: one shared refresh promise now serves auth bootstrap and 401 recovery; it resets in `finally`, does not recurse through `apiFetch`, and persists the returned CSRF token.
- `frontend/src/api/auth.ts`: auth bootstrap uses the shared refresh operation and preserves the existing session-expired error contract.
- `frontend/src/api/sources.ts`: source health and raw article requests accept fetch options.
- `frontend/src/features/sources/useSourcesQueries.ts`: forwards query cancellation signals to source health/articles requests.
- `frontend/src/telemetry/webVitals.ts`: observer registration is idempotent for the lifetime of the page.

## Regression coverage

- Concurrent refresh callers are asserted to share the same promise and produce exactly one fetch call.
- Repeated Web Vitals initialization is asserted to construct exactly three observers, not six.
- Canonical story ID validation remains covered by the existing frontend API test.

## Before / after measurement

- Auth: concurrent callers previously had no shared path during bootstrap; the regression test now runs two callers and measures 1 `/auth/refresh` fetch (rather than 2).
- Web Vitals: repeated initialization previously created 3 observers per call; the regression test now measures 3 total after two calls (rather than 6).
- Data queries: source health/articles now receive TanStack Query cancellation signals; stable tenant keys and the existing 5–10 minute freshness windows continue to provide in-flight/cache deduplication.

For a clean authenticated page load, the expected request count is now one refresh operation per concurrent bootstrap/recovery group and one active TanStack Query request per stable tenant-scoped resource. Navigating between content tabs reuses the cached `content/jobs` query for the configured freshness window instead of issuing a lifecycle duplicate.

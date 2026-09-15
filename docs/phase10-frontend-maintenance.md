# Phase 10 — Frontend maintenance cleanup

## Change

The frontend uses npm and a committed `package-lock.json`. Browserslist metadata was refreshed with `npx update-browserslist-db@latest`.

- `caniuse-lite`: `1.0.30001784` → `1.0.30001810`
- `baseline-browser-mapping`: `2.10.13` → `2.11.24`
- No application dependency or target-browser configuration changed.

The six-month Browserslist warning no longer appears when running the local Browserslist command.

## Validation

- `npx tsc --noEmit`: passed.
- `npm run build`: passed.
- `npm test -- --run`: 19 test files / 61 tests passed; 3 existing test files / 4 tests failed in query-key expectations, mobile navigation, and tab test behavior.
- `npm run lint`: existing failures in `e2e/fixtures/mockApi.ts`, `CommandPalette.tsx`, `QueryBoundary.tsx`, `features/sources/components.tsx`, plus existing warnings in content tabs and `SettingsPage.tsx`.

The lint/test failures are unrelated to the lockfile-only maintenance change and were not modified in this phase.

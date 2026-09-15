# Staged rollout gates (T8.2)

## Purpose

Gate multi-account and other high-risk production changes with explicit modes, reconciliation signals, and rollback criteria — without a parallel feature-flag product (platform module remains dormant).

## Multi-account modes

| Mode | Env `MULTI_ACCOUNT_ROLLOUT_MODE` | Behavior |
|------|----------------------------------|----------|
| off | `off` | One account per platform (legacy-safe collapse) |
| shadow | `shadow` | Serve multi-account; log/metric collapse delta |
| canary | `canary` | Multi-account for allowlist + `MULTI_ACCOUNT_CANARY_PERCENT` |
| on | `on` (default) | Full multi-account (shipped T4) |

Supporting env:

* `MULTI_ACCOUNT_CANARY_PERCENT` — 0–100 stable tenant hash bucket
* `MULTI_ACCOUNT_CANARY_TENANT_IDS` — comma-separated tenant UUIDs always in canary

Status surfaces: `GET /api/v1/health/config`, `GET /api/v1/health/metrics` → `runtime.multi_account_*`.

## Canary procedure

1. Deploy with `MULTI_ACCOUNT_ROLLOUT_MODE=shadow` for ≥1 soak window; confirm `/health/metrics` shadow ops and no publish ambiguity spike.
2. Switch to `canary` with allowlisted tenants, then raise percent 5 → 25 → 50.
3. Promote to `on` only when rollback signals stay clean for the soak window.
4. On trip: set `MULTI_ACCOUNT_ROLLOUT_MODE=off` (instant collapse) and open publish reconciler runbook.

## Migration reconciliation gate

1. CI unit: single Alembic head + revision chain + dormant tables absent from metadata (`test_migration_drift.py`).
2. CI integration (Postgres service): `CG_RUN_DB_MIGRATIONS=1` upgrades disposable DB to `head`.
3. Before prod migrate: take snapshot; run `alembic upgrade head` on canary DB; compare row counts for `social_accounts`, `publishing_jobs`, `published_posts`.
4. Abort if dual-write/backfill checksums diverge beyond documented tolerance.

## Rollback criteria (automated)

`backend.core.rollout.evaluate_rollback` on domain metrics snapshot:

| Signal | Default trip |
|--------|----------------|
| Publish ambiguous attempts | ≥ 5 |
| Account rate-limited | ≥ 50 |
| Provider failure ratio | ≥ 25% with ≥ 20 samples |

Operator drill: force stub provider failures in staging → confirm verdict `should_rollback=true` → flip mode to `off`.

## Regression pyramid (orchestration)

| Layer | Command | Covers |
|-------|---------|--------|
| Unit / policy | `make regression-unit` | markers default (no integration) |
| Integration | `make regression-integration` | Postgres/Redis when available |
| Frontend unit | `cd frontend && npm test -- --run` | components / access / parity |
| Domain E2E | `make e2e-ci` | Playwright chromium+mobile-chrome (mocked API) |
| Perf baselines | pytest `tests/benchmarks` | named thresholds from `docs/benchmarks` |
| Manifest | `test_regression_manifest.py` | risk areas keep owning tests |

Acceptance themes wired in CI: migration drift, tenant/account isolation, publish crash windows, worker recovery, API contracts, responsive E2E, performance baselines, rollout gates.

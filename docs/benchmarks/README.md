# Performance baselines (T0.2)

Versioned fixture: [`baseline.json`](./baseline.json).

## Offline CI

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/benchmarks
```

Stub harness validates named thresholds exist and structural query/provider budgets hold.

## Live capture (disposable Postgres)

1. Seed deterministic datasets described under each `scenarios.*.seed`.
2. Run `EXPLAIN (ANALYZE, BUFFERS)` for queries listed in `thresholds.sql_plans`.
3. Record provider call counts and wall p50/p95 with stubs or sandbox credentials.
4. Fill `observed_*` fields; set thresholds as `observed * regression_factor`.
5. Frontend: `npm run build` for chunk sizes; Playwright + browsers for Web Vitals.

Domain metric names, SLOs, and operator alerts: [`../observability/metrics.md`](../observability/metrics.md).

Do not run `EXPLAIN ANALYZE` against shared production data.

# Performance baselines

The versioned Phase 0 fixture is [baseline.json](./baseline.json). It records
measurements made before application-behavior changes, at commit
`598dbbbe53ec310038c0711823a7a3c88bcf2afd`.

The baseline deliberately separates three kinds of evidence:

- deterministic CPU/memory microbenchmarks that call current production helpers;
- PostgreSQL query evidence captured with `EXPLAIN (ANALYZE, BUFFERS)`;
- frontend build and browser measurements.

Do not compare numbers produced on different machines as though they were a
controlled before/after experiment. Use the same host, seed, build mode, and
commands for both sides of a performance change.

## Offline contract gate

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/benchmarks
```

This gate validates scenario coverage, non-null measurements, percentile order,
seed metadata, cache-ratio arithmetic, SQL-plan evidence, and thresholds derived
from observed p95 values. Phase 16 also enforces `db_query_count_max` architectural
ceilings (especially ingestion/dedupe/publishing/list flows) and Web Vitals /
bundle threshold derivation. It does not fail CI on noisy wall-clock measurements.

## Seeded backend microbenchmarks

```bash
PYTHONPATH=. backend/.venv/bin/python \
  backend/tests/benchmarks/capture_seeded_microbenchmarks.py
```

The script uses seed `20260915`, performs one warmup, then records ten samples.
It exercises the current ingestion normalization, nested duplicate matcher,
source trust calculation, story keyword extraction, content helpers, publishing
attempt-key construction, analytics synthetic metrics, and list serialization.
It prints raw samples plus p50/p95/p99 and peak traced memory. Copy results into
`baseline.json` only after reviewing them.

Provider calls and DB query counts in the fixture describe the current workflow
shape. Provider-dependent stages use deterministic stubs; no billable provider
is contacted.

## Disposable PostgreSQL capture

Never run `EXPLAIN ANALYZE` against shared or production data.

```bash
docker run -d --name cg-phase0-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=content_generator \
  -p 55432:5432 postgres:16

cd backend
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/content_generator \
  DB_POOL_USE_NULL=true CG_RUN_DB_MIGRATIONS=1 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q -m integration \
  tests/test_migration_drift.py

DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/content_generator \
  PYTHONPATH=. backend/.venv/bin/python \
  backend/tests/benchmarks/capture_sql_baseline.py
```

`capture_sql_baseline.py` inserts the fixed tenant
`00000000-0000-0000-0000-000000000001`, 100 due sources, and 10,000 raw articles
(`md5('source-' || n)::uuid` / `md5('article-' || n)::uuid`), runs `ANALYZE`,
captures the four important plans, and samples fresh connection checkout latency.
It refuses `localhost:5432` so shared databases are not measured by accident.

Phase 0 capture on this host:

| Query | Rows returned | Rows scanned | Execution |
| --- | ---: | ---: | ---: |
| due sources | 100 | 100 | 0.047 ms |
| duplicate collision lookup | 2 | 10,000 | 2.492 ms |
| raw-article list | 100 | 10,000 | 2.563 ms |
| stale publishing claims (empty seed) | 0 | 0 | 0.014 ms |

Checkout sample: p50 3.827 ms / p95 4.457 ms.

Any future index/query change must capture both pre-change and post-change plans
on the same seed. Adding an index without that comparison is not an accepted
optimization.

## Phase 2 index decisions (same seed)

Captured on disposable Postgres 16 with 10,000 `raw_articles` for tenant
`00000000-0000-0000-0000-000000000001`.

### Added: `ix_raw_articles_tenant_id_created_at`

Partial index `(tenant_id, created_at DESC, id DESC) WHERE deleted_at IS NULL`.

Supports `/sources/articles` keyset list and recent-article windows.

| Plan | Node | Rows returned | Rows scanned | Execution |
| --- | --- | ---: | ---: | ---: |
| pre | Seq Scan + Sort / Limit | 100 | 10,000 | 2.374 ms |
| post | Index Scan / Limit | 100 | 100 | 0.084 ms |

Selective: one tenant's live rows, ordered exactly as the query asks. Write cost
is one extra index maintain on article insert/soft-delete; accepted because the
list path previously sorted the full tenant pile.

### Skipped (measured, not selective enough yet)

| Query | Evidence | Decision |
| --- | --- | --- |
| sources list `(tenant_id, created_at)` | 100-row Seq Scan + Sort, 0.073 ms | skip; write amplification > benefit |
| fetch-run list `(tenant_id, created_at)` | empty relation on seed | skip until production volume justifies |
| latest publishing attempts | empty relation; unique `(publishing_job_id, attempt_number)` already exists | no extra index |

## Frontend bundle

```bash
cd frontend
npm ci
npm run build
```

Record decimal kB exactly as Vite reports it. Phase 0 produced a 279.76 kB entry
chunk (88.43 kB gzip) and a 399.68 kB largest chunk (108.42 kB gzip).

## Frontend Web Vitals

Use the production build or the same local Vite mode for every comparison. With
Chromium installed:

1. Register buffered `PerformanceObserver` instances through
   `page.addInitScript` for `largest-contentful-paint`, `layout-shift`, and
   `event`.
2. Navigate to `/` and wait for network idle.
3. Click the first visible button to produce one repeatable interaction.
4. Wait 250 ms, read the observers, close the page, and repeat for five cold
   pages.
5. Calculate nearest-rank p50/p95/p99 and update the fixture.

The Phase 0 sample was LCP p50 436 ms / p95 1,140 ms, INP p95 16 ms, and CLS p95
0.000365. These are local lab measurements, not field data.

## Pre-change quality gates

The full machine-readable ledger is in `pre_change_quality_gates` in the
fixture. Before Phase 0 behavior changes:

- backend unit (excluding later Phase 1 pagination async tests), named regression
  groups, migration drift, benchmark tests, frontend Vitest, and frontend build
  passed;
- Ruff failed with 70 findings;
- mypy failed with 165 findings in 25 files;
- frontend lint failed with 37 errors and one warning;
- Playwright failed during discovery because of malformed fixture input and an
  invalid nested device override.

Those failures are recorded, not silently treated as Phase 0 regressions.

Domain metric names, SLOs, and operator alerts are documented in
[../observability/metrics.md](../observability/metrics.md).

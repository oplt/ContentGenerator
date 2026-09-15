# Phase 8 — Dashboard and database performance

## Profile findings

The dashboard endpoints already had tenant-scoped indexes for the main status/date filters, and the story-cluster ranking query uses a bounded result set. No query plan evidence justified adding another index.

The concrete server-side bottleneck was `/content/jobs`: the route listed jobs, then called `get_job_detail()` for every job. Each detail call loaded assets and could issue another asset-group query. With the default 50-job page, this was 1 + 50–100 queries and repeated ORM/Pydantic work.

Analytics overview also loaded up to 100 published posts and filtered by `social_account_id` in Python when an account filter was supplied.

## Changes

- `ContentGenerationRepository` now loads assets and latest asset groups for all listed jobs using two bounded tenant-independent batch queries.
- `ContentGenerationService.list_job_details()` assembles the same response shape from those maps; single-job detail behavior remains unchanged.
- The content jobs route now performs one batched service call instead of a per-job detail loop.
- `PublishingRepository.list_published_posts()` accepts `social_account_id`, allowing `AnalyticsService.overview()` to push that predicate into SQL.

## Before / after measurement

- Content jobs: 1 + 50–100 queries for 50 jobs → 3 queries total (jobs, assets, groups).
- Account-filtered analytics posts: up to 100 rows loaded then filtered in Python → only matching rows selected by SQL, bounded by the existing limit.
- No index was added without an `EXPLAIN (ANALYZE, BUFFERS)` plan; the configured tenant/status/date indexes remain unchanged.

Regression tests guard against reintroducing the content-job N+1 route and verify the analytics account predicate is applied in the repository query.

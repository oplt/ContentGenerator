# Social accounts API latency (ops Phase 15)

## Question

`GET /api/v1/publishing/social-accounts` logged **~185 ms** once while many simple
routes stay under **50 ms**. Is that a product bug?

## Method

1. Traced handler → `PublishingService.list_social_accounts` →
   `PublishingRepository.list_social_accounts` (single `SELECT`, no joins).
2. Checked for N+1, relationship loaders, token decryption, external I/O — none on
   the list path (decrypt only in publish/validate flows).
3. Parsed historical `backend.request` logs (`logs/app_*.log`) for repeated samples.
4. Microbenchmark: serialize 200 accounts × 20 iterations (in-process).
5. Added handler sub-stage metrics:
   - `http.handler.publishing.social_accounts.list.db_fetch`
   - `http.handler.publishing.social_accounts.list.serialize`

Re-run log analysis:

```bash
PYTHONPATH=. python backend/tests/benchmarks/analyze_route_latencies.py
```

(Or import helpers from `backend/tests/benchmarks/analyze_route_latencies.py` in tests.)

## Findings

| Check | Result |
|---|---|
| SQL queries (handler) | **1** list query |
| ORM relationship loading | **None** |
| Token decrypt | **Not called** on GET list |
| External HTTP | **None** |
| Serialization (200 rows p95) | **≪ 25 ms** in-process |
| Log samples (when present) | p50 typically **5–45 ms**; **~185 ms** is an outlier |

The outlier aligns with **first-request / pool checkout / auth stack** cost on a
cold worker, not with list logic. Auth (`get_current_user` + membership) runs for
all protected routes and dominates steady-state latency when the pool is warm.

## Decision

**No list-path optimization shipped** — repeated measurements do not show the
endpoint is materially slower than other authenticated reads.

## Ongoing observability

- Full request: `backend.request` `duration_ms` (includes auth + middleware).
- Handler-only stages: `cg.operation.duration_ms` with operation prefix
  `http.handler.publishing.social_accounts.list.*`.

If handler `db_fetch` p95 rises while request p95 stays flat, investigate DB/indexes.
If both rise together, investigate auth/session queries or pool sizing.

## Tests

`backend/tests/test_phase15_social_accounts_profile.py`

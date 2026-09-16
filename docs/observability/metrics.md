# Domain metrics & operator runbook (T8.1)

## Ownership

| Area | Owner module | Primary signals |
|------|--------------|-----------------|
| Worker tasks | `backend/workers/runtime.py` | `cg.task.*` |
| HTTP providers | `backend/core/http.py` | `cg.provider.*` |
| Publishing / accounts | `publishing/attempt_lifecycle`, `job_executor` | `cg.publish.*` |
| Workflows | `workflows/observability.py` | `cg.operation.*` (`workflow.run` / `workflow.node` / `workflow.approval_wait` / `workflow.media` / `workflow.publish`) |
| Chess intelligence | `chess_intelligence/observability.py` | `cg.chess.import.total`, `cg.operation.*` (`chess.engine.analyze` / `chess.video.handoff`); provider HTTP via `cg.provider.*` |
| Tenant cache | `backend/core/tenant_cache.py` | `cg.cache.ops.total` |
| DB pool | `backend/db/session.py` | `cg.db.pool.events.total` |
| Inference | `inference/providers.py` | `cg.inference.event.total` |
| Web Vitals | `POST /health/web-vitals` | `cg.web_vitals.value` |

In-process snapshot: `GET /api/v1/health/metrics` → `domain`, `cache`, `http`, `db_pool`.
OTLP export when `OTLP_ENDPOINT` is set (`setup_telemetry`).

## Cardinality / privacy

**Allowed attributes:** `operation`, `outcome`, `error_class`, `provider`, `platform`, `queue`, `task`, `owner`, `result`, `event`, `status_class`, `rating`, `navigation_type`, `post_type`, `name`.

**Never tag:** `tenant_id`, user/account IDs, credentials, raw content, attempt keys, URLs with secrets. Correlation IDs belong on spans/logs (`X-Correlation-ID` / structlog / OTel baggage), not metric labels.

## SLOs (from `docs/benchmarks/baseline.json`)

| Flow | Signal | Budget |
|------|--------|--------|
| Publishing due jobs | `cg.task.duration_ms` (publish) / wall | p95 ≤ 10s |
| Analytics sync | provider + task duration | p95 ≤ 15s |
| Content generation | task duration | p95 ≤ 30s |
| Ingestion poll | task duration | p95 ≤ 5s |
| Cache | hit ratio by owner | ≥ 0.7 identity & content_strategy |
| Web Vitals | LCP / CLS / INP | 2500ms / 0.1 / 200ms p95 |

## Suggested alerts

1. **Publish ambiguity spike** — `cg.publish.attempt.total{outcome=ambiguous}` rate > baseline × 2 for 15m → run reconciler / check provider health.
2. **Account rate-limit storm** — `cg.publish.account_rate_limited.total` rising while other accounts idle → per-account quota / backoff.
3. **Provider 5xx / transport** — `cg.provider.request.total{outcome=failure|transport_error}` > 5% for 10m → circuit / dry-run.
4. **Cache miss collapse** — hit/(hit+miss) for `owner=identity|content_strategy` < 0.5 for 20m → Redis / TTL / invalidation storm.
5. **Queue delay** — `cg.task.queue_delay_ms` p95 > 2× wall budget when `enqueued_at` present → scale workers / check queue depth.
6. **Web Vitals regression** — LCP/CLS/INP p95 > baseline × 1.2 → frontend release rollback.

## Operator drill

1. Hit `GET /health/metrics` and confirm `domain.counters` / `histograms` populate after a publish or provider call.
2. Confirm response includes `X-Correlation-ID`; follow the same id in worker `TaskExecution.correlation_id` and logs.
3. From browser, load app shell; confirm `POST /health/web-vitals` receives LCP/CLS samples.
4. Simulate account quota exhaustion → expect `cg.publish.account_rate_limited.total` increment without dead-letter.
5. Disable OTLP (`OTLP_ENDPOINT=""`) → in-process snapshot still works (fail-open).

## Correlation path

`API CorrelationIdMiddleware` → structlog + OTel baggage/span → Celery `correlation_id` (task id or header) → `run_async_task` rebinds context → provider HTTP / DB work inherits logging context.

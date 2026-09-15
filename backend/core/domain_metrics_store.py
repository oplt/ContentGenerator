"""
Domain metrics facade (T8.1).

Always-on in-process counters/histograms for /health/metrics and tests.
When OpenTelemetry MeterProvider is configured, the same events are exported.

Cardinality / privacy rules
---------------------------
Allowed attributes (low-cardinality enums only):
  operation, outcome, error_class, provider, platform, queue, task,
  owner, result, event, status_class, rating, navigation_type, post_type

Forbidden as metric attributes:
  tenant_id, user_id, account ids, credentials, URLs with secrets, raw content,
  attempt keys, correlation ids (use span/log context instead)
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# --- Catalog (stable names; dashboards/alerts depend on these) ---

METRIC_OPERATION_DURATION = "cg.operation.duration_ms"
METRIC_OPERATION_TOTAL = "cg.operation.total"
METRIC_TASK_DURATION = "cg.task.duration_ms"
METRIC_TASK_TOTAL = "cg.task.total"
METRIC_TASK_QUEUE_DELAY = "cg.task.queue_delay_ms"
METRIC_PROVIDER_DURATION = "cg.provider.request.duration_ms"
METRIC_PROVIDER_TOTAL = "cg.provider.request.total"
METRIC_PROVIDER_RETRY = "cg.provider.retry.total"
METRIC_PUBLISH_ATTEMPT = "cg.publish.attempt.total"
METRIC_PUBLISH_RATE_LIMITED = "cg.publish.account_rate_limited.total"
METRIC_CACHE_OPS = "cg.cache.ops.total"
METRIC_DB_POOL = "cg.db.pool.events.total"
METRIC_INFERENCE_EVENT = "cg.inference.event.total"
METRIC_WEB_VITAL = "cg.web_vitals.value"
METRIC_CONTENT_VIDEO_DURATION = "cg.content.video_duration_ms"
METRIC_REQUEST_DURATION = "cg.request.duration_ms"
METRIC_REQUEST_TOTAL = "cg.request.total"
METRIC_DB_CHECKOUT_WAIT = "cg.db.checkout_wait_ms"
METRIC_DB_TX_DURATION = "cg.db.tx_duration_ms"
METRIC_DB_QUERY = "cg.db.query.total"
METRIC_DB_SLOW_QUERY = "cg.db.slow_query.total"
METRIC_HTTP_429 = "cg.http.429.total"
METRIC_SEMAPHORE_WAIT = "cg.provider.semaphore_wait_ms"
METRIC_INGESTION = "cg.ingestion.articles.total"
METRIC_PUBLISH_CLAIM = "cg.publish.claim.total"
METRIC_GENERATION_STAGE = "cg.content.stage.duration_ms"

ALLOWED_ATTR_KEYS = frozenset(
    {
        "operation",
        "outcome",
        "error_class",
        "provider",
        "platform",
        "queue",
        "task",
        "owner",
        "result",
        "event",
        "status_class",
        "rating",
        "navigation_type",
        "post_type",
        "name",
        "route",
        "method",
        "stage",
    }
)

_MAX_LABEL_LEN = 64


def _sanitize_attrs(attrs: Mapping[str, str] | None) -> dict[str, str]:
    if not attrs:
        return {}
    out: dict[str, str] = {}
    for key, value in attrs.items():
        if key not in ALLOWED_ATTR_KEYS:
            continue
        text = str(value or "unknown").strip().lower()[:_MAX_LABEL_LEN] or "unknown"
        out[key] = text
    return out


def _attr_key(attrs: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(attrs.items()))


@dataclass
class _HistogramAgg:
    count: int = 0
    sum_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0

    def observe(self, value_ms: float) -> None:
        if self.count == 0:
            self.min_ms = value_ms
            self.max_ms = value_ms
        else:
            self.min_ms = min(self.min_ms, value_ms)
            self.max_ms = max(self.max_ms, value_ms)
        self.count += 1
        self.sum_ms += value_ms


@dataclass
class _InMemoryStore:
    counters: dict[str, dict[tuple[tuple[str, str], ...], int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    histograms: dict[str, dict[tuple[tuple[str, str], ...], _HistogramAgg]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_counter(self, name: str, amount: int, attrs: dict[str, str]) -> None:
        key = _attr_key(attrs)
        with self.lock:
            self.counters[name][key] += amount

    def observe(self, name: str, value_ms: float, attrs: dict[str, str]) -> None:
        key = _attr_key(attrs)
        with self.lock:
            bucket = self.histograms[name].get(key)
            if bucket is None:
                bucket = _HistogramAgg()
                self.histograms[name][key] = bucket
            bucket.observe(value_ms)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            counters = {
                name: [
                    {"attrs": dict(attrs), "value": value}
                    for attrs, value in sorted(series.items(), key=lambda item: item[0])
                ]
                for name, series in sorted(self.counters.items())
            }
            histograms = {
                name: [
                    {
                        "attrs": dict(attrs),
                        "count": agg.count,
                        "sum_ms": round(agg.sum_ms, 3),
                        "min_ms": round(agg.min_ms, 3),
                        "max_ms": round(agg.max_ms, 3),
                        "avg_ms": round(agg.sum_ms / agg.count, 3) if agg.count else 0.0,
                    }
                    for attrs, agg in sorted(series.items(), key=lambda item: item[0])
                ]
                for name, series in sorted(self.histograms.items())
            }
        return {"counters": counters, "histograms": histograms}

    def reset(self) -> None:
        with self.lock:
            self.counters.clear()
            self.histograms.clear()



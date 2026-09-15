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
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
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


class DomainMetrics:
    """Process-local + optional OTel domain metrics."""

    def __init__(self) -> None:
        self._store = _InMemoryStore()
        self._otel_counters: dict[str, Any] = {}
        self._otel_histograms: dict[str, Any] = {}
        self._meter: Any | None = None

    def bind_otel_meter(self, meter: Any) -> None:
        """Attach an OpenTelemetry meter (idempotent)."""
        self._meter = meter
        definitions = (
            (METRIC_OPERATION_TOTAL, "Domain operation outcomes"),
            (METRIC_TASK_TOTAL, "Worker task outcomes"),
            (METRIC_PROVIDER_TOTAL, "Outbound provider request outcomes"),
            (METRIC_PROVIDER_RETRY, "Outbound provider retries"),
            (METRIC_PUBLISH_ATTEMPT, "Publishing attempt outcomes"),
            (METRIC_PUBLISH_RATE_LIMITED, "Account publish quota deferrals"),
            (METRIC_CACHE_OPS, "Tenant cache operations"),
            (METRIC_DB_POOL, "Database pool events"),
            (METRIC_INFERENCE_EVENT, "Inference parse/provider events"),
        )
        hist_defs = (
            (METRIC_OPERATION_DURATION, "Domain operation duration"),
            (METRIC_TASK_DURATION, "Worker task duration"),
            (METRIC_TASK_QUEUE_DELAY, "Worker queue delay"),
            (METRIC_PROVIDER_DURATION, "Provider request duration"),
            (METRIC_WEB_VITAL, "Frontend Web Vital sample"),
            (METRIC_CONTENT_VIDEO_DURATION, "Published video asset duration"),
        )
        for name, description in definitions:
            try:
                self._otel_counters[name] = meter.create_counter(name, description=description, unit="1")
            except Exception as exc:  # pragma: no cover - exporter quirks
                logger.debug("otel_counter_skip name=%s error=%s", name, exc)
        for name, description in hist_defs:
            try:
                self._otel_histograms[name] = meter.create_histogram(
                    name, description=description, unit="ms"
                )
            except Exception as exc:  # pragma: no cover
                logger.debug("otel_histogram_skip name=%s error=%s", name, exc)

    def reset(self) -> None:
        self._store.reset()

    def snapshot(self) -> dict[str, Any]:
        return self._store.snapshot()

    def _inc(self, name: str, attrs: Mapping[str, str] | None = None, *, amount: int = 1) -> None:
        clean = _sanitize_attrs(attrs)
        self._store.add_counter(name, amount, clean)
        instrument = self._otel_counters.get(name)
        if instrument is not None:
            try:
                instrument.add(amount, attributes=clean)
            except Exception as exc:  # pragma: no cover
                logger.debug("otel_counter_emit_failed name=%s error=%s", name, exc)

    def _observe(self, name: str, value_ms: float, attrs: Mapping[str, str] | None = None) -> None:
        if value_ms < 0:
            value_ms = 0.0
        clean = _sanitize_attrs(attrs)
        self._store.observe(name, value_ms, clean)
        instrument = self._otel_histograms.get(name)
        if instrument is not None:
            try:
                instrument.record(value_ms, attributes=clean)
            except Exception as exc:  # pragma: no cover
                logger.debug("otel_histogram_emit_failed name=%s error=%s", name, exc)

    # --- Domain helpers ---

    def record_operation(
        self,
        operation: str,
        *,
        outcome: str,
        duration_ms: float,
        error_class: str | None = None,
    ) -> None:
        attrs: dict[str, str] = {"operation": operation, "outcome": outcome}
        if error_class:
            attrs["error_class"] = error_class
        self._inc(METRIC_OPERATION_TOTAL, attrs)
        self._observe(METRIC_OPERATION_DURATION, duration_ms, attrs)

    def record_task(
        self,
        *,
        task: str,
        queue: str,
        outcome: str,
        duration_ms: float,
        queue_delay_ms: float | None = None,
    ) -> None:
        attrs = {"task": task, "queue": queue, "outcome": outcome}
        self._inc(METRIC_TASK_TOTAL, attrs)
        self._observe(METRIC_TASK_DURATION, duration_ms, attrs)
        if queue_delay_ms is not None:
            self._observe(METRIC_TASK_QUEUE_DELAY, queue_delay_ms, {"task": task, "queue": queue})

    def record_provider_request(
        self,
        *,
        provider: str,
        outcome: str,
        duration_ms: float,
        status_class: str = "none",
    ) -> None:
        attrs = {
            "provider": provider,
            "outcome": outcome,
            "status_class": status_class,
        }
        self._inc(METRIC_PROVIDER_TOTAL, attrs)
        self._observe(METRIC_PROVIDER_DURATION, duration_ms, attrs)

    def record_provider_retry(self, *, provider: str, reason: str) -> None:
        self._inc(METRIC_PROVIDER_RETRY, {"provider": provider, "result": reason})

    def record_publish_attempt(
        self,
        *,
        platform: str,
        outcome: str,
        error_class: str | None = None,
        post_type: str | None = None,
    ) -> None:
        attrs: dict[str, str] = {"platform": platform, "outcome": outcome}
        if error_class:
            attrs["error_class"] = error_class
        if post_type:
            attrs["post_type"] = post_type
        self._inc(METRIC_PUBLISH_ATTEMPT, attrs)

    def record_publish_rate_limited(self, *, platform: str) -> None:
        self._inc(METRIC_PUBLISH_RATE_LIMITED, {"platform": platform})

    def record_cache(self, *, owner: str, result: str) -> None:
        self._inc(METRIC_CACHE_OPS, {"owner": owner, "result": result})

    def record_db_pool(self, *, event: str) -> None:
        self._inc(METRIC_DB_POOL, {"event": event})

    def record_inference_event(self, *, provider: str, event: str) -> None:
        self._inc(METRIC_INFERENCE_EVENT, {"provider": provider, "event": event})

    def record_web_vital(
        self,
        *,
        name: str,
        value: float,
        rating: str = "unknown",
        navigation_type: str = "unknown",
    ) -> None:
        attrs = {
            "name": name,
            "rating": rating,
            "navigation_type": navigation_type,
        }
        self._observe(METRIC_WEB_VITAL, float(value), attrs)

    def record_video_duration(self, *, platform: str, duration_ms: float) -> None:
        self._observe(
            METRIC_CONTENT_VIDEO_DURATION,
            duration_ms,
            {"platform": platform, "post_type": "video"},
        )

    @contextmanager
    def measure_operation(self, operation: str) -> Iterator[dict[str, str]]:
        """Context manager that records duration + outcome (success unless marked)."""
        state: dict[str, str] = {"outcome": "success"}
        started = time.perf_counter()
        try:
            yield state
        except Exception:
            state["outcome"] = "failure"
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self.record_operation(
                operation,
                outcome=state.get("outcome", "success"),
                duration_ms=duration_ms,
                error_class=state.get("error_class"),
            )


domain_metrics = DomainMetrics()


def get_domain_metrics_snapshot() -> dict[str, Any]:
    return domain_metrics.snapshot()


def reset_domain_metrics() -> None:
    domain_metrics.reset()

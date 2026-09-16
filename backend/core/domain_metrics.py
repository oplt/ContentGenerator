"""Domain metrics facade (T8.1): in-process + optional OTel export.

Allowed attrs (low-cardinality): operation, outcome, error_class, provider,
platform, queue, task, owner, result, event, status_class, rating,
navigation_type, post_type, name, route, method, stage, model.
Forbidden: tenant/user ids, credentials, secret URLs, raw content.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from backend.core.domain_metrics_obs import ObservabilityMetricsMixin
from backend.core.domain_metrics_store import (
    ALLOWED_ATTR_KEYS,
    METRIC_CACHE_OPS,
    METRIC_CONTENT_VIDEO_DURATION,
    METRIC_DB_CHECKOUT_WAIT,
    METRIC_DB_POOL,
    METRIC_DB_QUERY,
    METRIC_DB_SLOW_QUERY,
    METRIC_DB_TX_DURATION,
    METRIC_GENERATION_STAGE,
    METRIC_HTTP_429,
    METRIC_INFERENCE_EVENT,
    METRIC_INGESTION,
    METRIC_INGESTION_STAGE,
    METRIC_LLM_CALL,
    METRIC_OPERATION_DURATION,
    METRIC_OPERATION_TOTAL,
    METRIC_PROVIDER_DURATION,
    METRIC_PROVIDER_RETRY,
    METRIC_PROVIDER_TOTAL,
    METRIC_PUBLISH_ATTEMPT,
    METRIC_PUBLISH_CLAIM,
    METRIC_PUBLISH_RATE_LIMITED,
    METRIC_REQUEST_DURATION,
    METRIC_REQUEST_TOTAL,
    METRIC_SEMAPHORE_WAIT,
    METRIC_TASK_DURATION,
    METRIC_TASK_QUEUE_DELAY,
    METRIC_TASK_TOTAL,
    METRIC_WEB_VITAL,
    METRIC_CHESS_IMPORT,
    _InMemoryStore,
    _sanitize_attrs,
)

logger = logging.getLogger(__name__)

# Re-export catalog for callers/tests.
__all__ = [
    "ALLOWED_ATTR_KEYS",
    "DomainMetrics",
    "domain_metrics",
    "get_domain_metrics_snapshot",
    "reset_domain_metrics",
    "METRIC_CACHE_OPS",
    "METRIC_CONTENT_VIDEO_DURATION",
    "METRIC_DB_CHECKOUT_WAIT",
    "METRIC_DB_POOL",
    "METRIC_DB_QUERY",
    "METRIC_DB_SLOW_QUERY",
    "METRIC_DB_TX_DURATION",
    "METRIC_GENERATION_STAGE",
    "METRIC_HTTP_429",
    "METRIC_INFERENCE_EVENT",
    "METRIC_INGESTION",
    "METRIC_OPERATION_DURATION",
    "METRIC_OPERATION_TOTAL",
    "METRIC_PROVIDER_DURATION",
    "METRIC_PROVIDER_RETRY",
    "METRIC_PROVIDER_TOTAL",
    "METRIC_PUBLISH_ATTEMPT",
    "METRIC_PUBLISH_CLAIM",
    "METRIC_PUBLISH_RATE_LIMITED",
    "METRIC_REQUEST_DURATION",
    "METRIC_REQUEST_TOTAL",
    "METRIC_SEMAPHORE_WAIT",
    "METRIC_TASK_DURATION",
    "METRIC_TASK_QUEUE_DELAY",
    "METRIC_TASK_TOTAL",
    "METRIC_WEB_VITAL",
    "METRIC_CHESS_IMPORT",
]


class DomainMetrics(ObservabilityMetricsMixin):
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
            (METRIC_REQUEST_TOTAL, "HTTP request outcomes"),
            (METRIC_DB_QUERY, "Database query executions"),
            (METRIC_DB_SLOW_QUERY, "Slow database queries"),
            (METRIC_HTTP_429, "Outbound HTTP 429 responses"),
            (METRIC_INGESTION, "Ingestion article outcomes"),
            (METRIC_PUBLISH_CLAIM, "Publishing claim/recovery events"),
            (METRIC_CHESS_IMPORT, "Chess game/puzzle import and video handoff counts"),
        )
        hist_defs = (
            (METRIC_OPERATION_DURATION, "Domain operation duration"),
            (METRIC_TASK_DURATION, "Worker task duration"),
            (METRIC_TASK_QUEUE_DELAY, "Worker queue delay"),
            (METRIC_PROVIDER_DURATION, "Provider request duration"),
            (METRIC_WEB_VITAL, "Frontend Web Vital sample"),
            (METRIC_CONTENT_VIDEO_DURATION, "Published video asset duration"),
            (METRIC_REQUEST_DURATION, "HTTP request duration"),
            (METRIC_DB_CHECKOUT_WAIT, "DB pool checkout wait"),
            (METRIC_DB_TX_DURATION, "DB transaction duration"),
            (METRIC_SEMAPHORE_WAIT, "Provider semaphore wait"),
            (METRIC_GENERATION_STAGE, "Content generation stage duration"),
            (METRIC_INGESTION_STAGE, "Ingestion pipeline stage duration"),
            (METRIC_LLM_CALL, "LLM/embedding call duration"),
        )
        for name, description in definitions:
            try:
                self._otel_counters[name] = meter.create_counter(
                    name, description=description, unit="1"
                )
            except Exception as exc:  # pragma: no cover
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
        attrs = {"provider": provider, "outcome": outcome, "status_class": status_class}
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
        self._observe(
            METRIC_WEB_VITAL,
            float(value),
            {"name": name, "rating": rating, "navigation_type": navigation_type},
        )

    def record_video_duration(self, *, platform: str, duration_ms: float) -> None:
        self._observe(
            METRIC_CONTENT_VIDEO_DURATION,
            duration_ms,
            {"platform": platform, "post_type": "video"},
        )

    def record_chess_import(
        self,
        *,
        kind: str,
        provider: str,
        result: str,
        amount: int = 1,
        operation: str | None = None,
    ) -> None:
        """Chess catalog import / handoff counters (low-cardinality attrs only)."""
        if amount <= 0:
            return
        self._inc(
            METRIC_CHESS_IMPORT,
            {
                "operation": (operation or f"chess.{kind}.import")[:64],
                "provider": provider,
                "result": result,
            },
            amount=amount,
        )

    @contextmanager
    def measure_operation(self, operation: str) -> Iterator[dict[str, str]]:
        """Record duration + outcome (success unless marked)."""
        state: dict[str, str] = {"outcome": "success"}
        started = time.perf_counter()
        try:
            yield state
        except Exception:
            state["outcome"] = "failure"
            raise
        finally:
            self.record_operation(
                operation,
                outcome=state.get("outcome", "success"),
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error_class=state.get("error_class"),
            )


domain_metrics = DomainMetrics()


def get_domain_metrics_snapshot() -> dict[str, Any]:
    return domain_metrics.snapshot()


def reset_domain_metrics() -> None:
    domain_metrics.reset()

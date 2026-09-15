"""Phase 15 bottleneck metric helpers (keeps domain_metrics facade lean)."""

from __future__ import annotations

from collections.abc import Mapping

from backend.core.domain_metrics_store import (
    METRIC_DB_CHECKOUT_WAIT,
    METRIC_DB_QUERY,
    METRIC_DB_SLOW_QUERY,
    METRIC_DB_TX_DURATION,
    METRIC_GENERATION_STAGE,
    METRIC_HTTP_429,
    METRIC_INGESTION,
    METRIC_PUBLISH_CLAIM,
    METRIC_REQUEST_DURATION,
    METRIC_REQUEST_TOTAL,
    METRIC_SEMAPHORE_WAIT,
)


class ObservabilityMetricsMixin:
    """Request / DB / HTTP / domain-flow recording (low-cardinality attrs only)."""

    def _inc(self, name: str, attrs: Mapping[str, str] | None = None, *, amount: int = 1) -> None: ...

    def _observe(self, name: str, value_ms: float, attrs: Mapping[str, str] | None = None) -> None: ...

    def record_request(
        self,
        *,
        method: str,
        route: str,
        status_class: str,
        duration_ms: float,
    ) -> None:
        attrs = {"method": method, "route": route, "status_class": status_class}
        self._inc(METRIC_REQUEST_TOTAL, attrs)
        self._observe(METRIC_REQUEST_DURATION, duration_ms, attrs)

    def record_db_checkout_wait(self, *, duration_ms: float) -> None:
        self._observe(METRIC_DB_CHECKOUT_WAIT, duration_ms)

    def record_db_tx(self, *, outcome: str, duration_ms: float) -> None:
        self._observe(METRIC_DB_TX_DURATION, duration_ms, {"outcome": outcome})

    def record_db_query(self, *, amount: int = 1) -> None:
        self._inc(METRIC_DB_QUERY, amount=amount)

    def record_db_slow_query(self, *, amount: int = 1) -> None:
        self._inc(METRIC_DB_SLOW_QUERY, amount=amount)

    def record_http_429(self, *, provider: str) -> None:
        self._inc(METRIC_HTTP_429, {"provider": provider})

    def record_semaphore_wait(self, *, provider: str, duration_ms: float) -> None:
        self._observe(METRIC_SEMAPHORE_WAIT, duration_ms, {"provider": provider})

    def record_ingestion(self, *, result: str, amount: int = 1) -> None:
        if amount <= 0:
            return
        self._inc(METRIC_INGESTION, {"result": result}, amount=amount)

    def record_publish_claim(self, *, event: str, amount: int = 1) -> None:
        if amount <= 0:
            return
        self._inc(METRIC_PUBLISH_CLAIM, {"event": event}, amount=amount)

    def record_generation_stage(
        self,
        *,
        stage: str,
        duration_ms: float,
        outcome: str = "success",
    ) -> None:
        attrs = {"stage": stage, "outcome": outcome}
        self._observe(METRIC_GENERATION_STAGE, duration_ms, attrs)

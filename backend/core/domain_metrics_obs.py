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
    METRIC_INGESTION_STAGE,
    METRIC_LLM_CALL,
    METRIC_OPERATION_DURATION,
    METRIC_OPERATION_TOTAL,
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

    def record_ingestion_stage(
        self,
        *,
        stage: str,
        duration_ms: float,
        outcome: str = "success",
    ) -> None:
        attrs = {"stage": stage, "outcome": outcome}
        self._observe(METRIC_INGESTION_STAGE, duration_ms, attrs)

    def record_llm_call(
        self,
        *,
        provider: str,
        model: str,
        operation: str,
        duration_ms: float,
        outcome: str = "success",
    ) -> None:
        """Duration of one LLM/embedding call — never include prompt text."""
        attrs = {
            "provider": provider,
            "model": model[:64],
            "operation": operation[:64],
            "outcome": outcome,
        }
        self._observe(METRIC_LLM_CALL, duration_ms, attrs)

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

    def record_workflow_run(
        self,
        *,
        outcome: str,
        duration_ms: float,
        error_class: str | None = None,
    ) -> None:
        attrs = {"operation": "workflow.run", "outcome": outcome}
        if error_class:
            attrs["error_class"] = error_class
        self._inc(METRIC_OPERATION_TOTAL, attrs)
        if duration_ms > 0:
            self._observe(METRIC_OPERATION_DURATION, duration_ms, attrs)

    def record_workflow_node(
        self,
        *,
        node_type: str,
        outcome: str,
        duration_ms: float,
        event: str | None = None,
    ) -> None:
        attrs = {
            "operation": "workflow.node",
            "outcome": outcome,
            "stage": node_type,
        }
        if event:
            attrs["event"] = event
        self._inc(METRIC_OPERATION_TOTAL, attrs)
        self._observe(METRIC_OPERATION_DURATION, duration_ms, attrs)

    def record_workflow_approval_wait(self, *, duration_ms: float, outcome: str) -> None:
        attrs = {"operation": "workflow.approval_wait", "outcome": outcome}
        self._inc(METRIC_OPERATION_TOTAL, attrs)
        self._observe(METRIC_OPERATION_DURATION, duration_ms, attrs)

    def record_workflow_media(
        self,
        *,
        node_type: str,
        outcome: str,
        duration_ms: float,
    ) -> None:
        attrs = {
            "operation": "workflow.media",
            "outcome": outcome,
            "stage": node_type,
        }
        self._inc(METRIC_OPERATION_TOTAL, attrs)
        self._observe(METRIC_OPERATION_DURATION, duration_ms, attrs)

    def record_workflow_publish_failure(self, *, platform: str = "unknown") -> None:
        self._inc(
            METRIC_OPERATION_TOTAL,
            {
                "operation": "workflow.publish",
                "outcome": "failure",
                "platform": platform,
            },
        )

    def record_workflow_publish_job(
        self,
        *,
        outcome: str = "success",
        platform: str = "unknown",
        amount: int = 1,
    ) -> None:
        if amount <= 0:
            return
        self._inc(
            METRIC_OPERATION_TOTAL,
            {
                "operation": "workflow.publish",
                "outcome": outcome,
                "platform": platform,
            },
            amount=amount,
        )

    def record_workflow_node_claim_expiration(self, *, amount: int = 1) -> None:
        if amount <= 0:
            return
        self._inc(
            METRIC_OPERATION_TOTAL,
            {
                "operation": "workflow.node.claim_expiration",
                "outcome": "expired",
                "event": "claim_expired",
            },
            amount=amount,
        )

    def record_workflow_node_stale_recovery(
        self,
        *,
        action: str,
        amount: int = 1,
    ) -> None:
        if amount <= 0:
            return
        self._inc(
            METRIC_OPERATION_TOTAL,
            {
                "operation": "workflow.node.stale_recovery",
                "outcome": action,
                "event": "stale_recovery",
            },
            amount=amount,
        )

    def record_workflow_wait(
        self,
        *,
        wait_type: str,
        outcome: str,
        duration_ms: float,
    ) -> None:
        attrs = {
            "operation": "workflow.wait",
            "outcome": outcome,
            "stage": wait_type[:64],
        }
        self._inc(METRIC_OPERATION_TOTAL, attrs)
        self._observe(METRIC_OPERATION_DURATION, duration_ms, attrs)

    def record_workflow_scheduler_occurrence(self, *, outcome: str) -> None:
        self._inc(
            METRIC_OPERATION_TOTAL,
            {"operation": "workflow.scheduler.occurrence", "outcome": outcome},
        )

    def record_workflow_scheduler_lag(self, *, lag_ms: float) -> None:
        self._observe(
            METRIC_OPERATION_DURATION,
            max(0.0, lag_ms),
            {"operation": "workflow.scheduler.lag", "outcome": "observed"},
        )

    def record_workflow_llm_call(
        self,
        *,
        node_type: str,
        outcome: str,
        duration_ms: float,
        provider: str = "unknown",
    ) -> None:
        attrs = {
            "operation": "workflow.llm",
            "outcome": outcome,
            "stage": node_type[:64],
            "provider": provider[:64],
        }
        self._inc(METRIC_OPERATION_TOTAL, attrs)
        self._observe(METRIC_OPERATION_DURATION, duration_ms, attrs)

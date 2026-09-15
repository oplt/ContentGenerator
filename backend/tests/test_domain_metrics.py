"""T8.1 domain metrics unit tests."""

from __future__ import annotations

from backend.core.domain_metrics import (
    ALLOWED_ATTR_KEYS,
    METRIC_CACHE_OPS,
    METRIC_PROVIDER_TOTAL,
    METRIC_PUBLISH_ATTEMPT,
    METRIC_TASK_TOTAL,
    domain_metrics,
    reset_domain_metrics,
)
from backend.core.telemetry import bind_correlation_context, setup_telemetry


def setup_function() -> None:
    reset_domain_metrics()


def test_sanitize_drops_forbidden_attrs() -> None:
    domain_metrics.record_task(
        task="publish_due_jobs",
        queue="publishing",
        outcome="success",
        duration_ms=12.5,
    )
    domain_metrics._inc(  # noqa: SLF001 — intentional cardinality check
        METRIC_TASK_TOTAL,
        {"task": "x", "tenant_id": "secret-tenant", "outcome": "success"},
    )
    snap = domain_metrics.snapshot()
    for row in snap["counters"][METRIC_TASK_TOTAL]:
        assert "tenant_id" not in row["attrs"]
        assert set(row["attrs"]).issubset(ALLOWED_ATTR_KEYS)


def test_record_provider_and_publish() -> None:
    domain_metrics.record_provider_request(
        provider="x",
        outcome="success",
        duration_ms=40.0,
        status_class="2xx",
    )
    domain_metrics.record_publish_attempt(
        platform="x",
        outcome="success",
        post_type="text",
    )
    domain_metrics.record_publish_rate_limited(platform="x")
    domain_metrics.record_cache(owner="identity", result="hit")
    snap = domain_metrics.snapshot()
    assert METRIC_PROVIDER_TOTAL in snap["counters"]
    assert METRIC_PUBLISH_ATTEMPT in snap["counters"]
    assert METRIC_CACHE_OPS in snap["counters"]
    assert any(row["attrs"].get("result") == "hit" for row in snap["counters"][METRIC_CACHE_OPS])


def test_measure_operation_success_and_failure() -> None:
    with domain_metrics.measure_operation("ingestion.poll") as state:
        state["outcome"] = "success"
    try:
        with domain_metrics.measure_operation("ingestion.poll"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    snap = domain_metrics.snapshot()
    outcomes = {
        row["attrs"]["outcome"]
        for row in snap["counters"]["cg.operation.total"]
        if row["attrs"].get("operation") == "ingestion.poll"
    }
    assert "success" in outcomes
    assert "failure" in outcomes


def test_web_vital_recording() -> None:
    domain_metrics.record_web_vital(
        name="lcp",
        value=1200.0,
        rating="good",
        navigation_type="navigate",
    )
    snap = domain_metrics.snapshot()
    assert "cg.web_vitals.value" in snap["histograms"]
    row = snap["histograms"]["cg.web_vitals.value"][0]
    assert row["attrs"]["name"] == "lcp"
    assert row["count"] == 1


def test_setup_telemetry_binds_without_otlp(monkeypatch) -> None:
    from backend.core import config

    monkeypatch.setattr(config.settings, "OTLP_ENDPOINT", "")
    monkeypatch.setattr(config.settings, "SENTRY_DSN", "")
    setup_telemetry(app=None)
    domain_metrics.record_task(
        task="noop",
        queue="default",
        outcome="success",
        duration_ms=1.0,
    )
    assert domain_metrics.snapshot()["counters"][METRIC_TASK_TOTAL]


def test_bind_correlation_context_does_not_raise() -> None:
    bind_correlation_context("corr-test-123")
    bind_correlation_context(None)


def test_queue_delay_from_payload() -> None:
    import time

    from backend.workers.runtime import _queue_delay_ms

    assert _queue_delay_ms(None) is None
    assert _queue_delay_ms({"enqueued_at": "nope"}) is None
    delay = _queue_delay_ms({"enqueued_at": str(time.time() - 1.5)})
    assert delay is not None
    assert 1000.0 <= delay <= 5000.0

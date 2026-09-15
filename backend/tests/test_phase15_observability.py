"""Phase 15 — bottleneck metrics + structured log redaction."""

from __future__ import annotations

from backend.api.middleware.request_logging import _route_label
from backend.core.domain_metrics import (
    METRIC_DB_CHECKOUT_WAIT,
    METRIC_GENERATION_STAGE,
    METRIC_HTTP_429,
    METRIC_INGESTION,
    METRIC_PUBLISH_CLAIM,
    METRIC_REQUEST_DURATION,
    METRIC_SEMAPHORE_WAIT,
    domain_metrics,
    reset_domain_metrics,
)
from backend.core.log_context import drop_sensitive_log_keys
from backend.modules.content_generation.workflow_stages import generation_stage


def setup_function() -> None:
    reset_domain_metrics()


def test_record_request_latency_by_route() -> None:
    domain_metrics.record_request(
        method="GET",
        route="/api/v1/health",
        status_class="2xx",
        duration_ms=12.5,
    )
    snap = domain_metrics.snapshot()
    assert METRIC_REQUEST_DURATION in snap["histograms"]
    row = snap["histograms"][METRIC_REQUEST_DURATION][0]
    assert row["attrs"]["route"] == "/api/v1/health"
    assert row["attrs"]["method"] == "get"


def test_record_db_checkout_and_tx() -> None:
    domain_metrics.record_db_checkout_wait(duration_ms=3.0)
    domain_metrics.record_db_tx(outcome="success", duration_ms=40.0)
    domain_metrics.record_db_query(amount=2)
    domain_metrics.record_db_slow_query()
    snap = domain_metrics.snapshot()
    assert METRIC_DB_CHECKOUT_WAIT in snap["histograms"]
    assert snap["counters"]["cg.db.query.total"][0]["value"] == 2
    assert snap["counters"]["cg.db.slow_query.total"][0]["value"] == 1


def test_http_429_and_semaphore_wait() -> None:
    domain_metrics.record_http_429(provider="x")
    domain_metrics.record_semaphore_wait(provider="x", duration_ms=5.0)
    snap = domain_metrics.snapshot()
    assert snap["counters"][METRIC_HTTP_429][0]["attrs"]["provider"] == "x"
    assert METRIC_SEMAPHORE_WAIT in snap["histograms"]


def test_ingestion_and_publish_claim_counts() -> None:
    domain_metrics.record_ingestion(result="fetched", amount=10)
    domain_metrics.record_ingestion(result="accepted", amount=7)
    domain_metrics.record_ingestion(result="duplicate", amount=3)
    domain_metrics.record_publish_claim(event="claimed", amount=2)
    domain_metrics.record_publish_claim(event="recovered", amount=1)
    snap = domain_metrics.snapshot()
    results = {
        row["attrs"]["result"]: row["value"] for row in snap["counters"][METRIC_INGESTION]
    }
    assert results == {"accepted": 7, "duplicate": 3, "fetched": 10}
    events = {
        row["attrs"]["event"]: row["value"] for row in snap["counters"][METRIC_PUBLISH_CLAIM]
    }
    assert events == {"claimed": 2, "recovered": 1}


def test_generation_stage_context_records_duration() -> None:
    with generation_stage("prepare"):
        pass
    try:
        with generation_stage("llm_generation"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    snap = domain_metrics.snapshot()
    stages = {
        row["attrs"]["stage"]: row["attrs"]["outcome"]
        for row in snap["histograms"][METRIC_GENERATION_STAGE]
    }
    assert stages["prepare"] == "success"
    assert stages["llm_generation"] == "failure"


def test_drop_sensitive_log_keys() -> None:
    event = drop_sensitive_log_keys(
        None,
        "info",
        {
            "event": "login",
            "password": "secret",
            "api_key": "k",
            "authorization": "Bearer x",
            "refresh_token": "t",
            "tenant_id": "ok",
        },
    )
    assert event["password"] == "[redacted]"
    assert event["api_key"] == "[redacted]"
    assert event["authorization"] == "[redacted]"
    assert event["refresh_token"] == "[redacted]"
    assert event["tenant_id"] == "ok"


def test_route_label_collapses_uuids() -> None:
    class _Req:
        scope: dict[str, object] = {}
        url = type("u", (), {"path": "/api/v1/jobs/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"})()

    assert "{id}" in _route_label(_Req())  # type: ignore[arg-type]

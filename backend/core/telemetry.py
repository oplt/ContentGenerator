from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CORRELATION_ATTR = "correlation_id"


def setup_telemetry(app: Any = None) -> None:
    from backend.core.config import settings
    from backend.core.domain_metrics import domain_metrics

    _setup_sentry(
        settings.SENTRY_DSN,
        settings.APP_ENV,
        settings.SENTRY_TRACES_SAMPLE_RATE,
    )
    meter = _setup_otel(
        settings.OTLP_ENDPOINT,
        settings.OTEL_SERVICE_NAME,
        settings.OTLP_INSECURE,
        app,
    )
    if meter is None:
        meter = _ensure_local_meter(settings.OTEL_SERVICE_NAME)
    if meter is not None:
        domain_metrics.bind_otel_meter(meter)


def _ensure_local_meter(service_name: str) -> Any | None:
    """No-export MeterProvider so instruments register even without OTLP."""
    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        provider = metrics.get_meter_provider()
        if type(provider).__name__ == "ProxyMeterProvider" or not isinstance(provider, MeterProvider):
            metrics.set_meter_provider(
                MeterProvider(resource=Resource(attributes={SERVICE_NAME: service_name}))
            )
        return metrics.get_meter("content_generator.domain")
    except Exception:
        logger.debug("domain_metrics_otel_bind_skipped", exc_info=True)
        return None


def bind_correlation_context(correlation_id: str | None) -> None:
    """Attach correlation id to structlog + current OTel span (if any)."""
    if not correlation_id:
        return
    try:
        import structlog

        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    except Exception:
        pass
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is not None and span.is_recording():
            span.set_attribute(CORRELATION_ATTR, correlation_id)
    except Exception:
        pass
    try:
        from opentelemetry import baggage
        from opentelemetry.context import attach, get_current

        attach(baggage.set_baggage(CORRELATION_ATTR, correlation_id, context=get_current()))
    except Exception:
        pass


def _setup_sentry(dsn: str, environment: str, traces_sample_rate: float) -> None:
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("sentry-sdk not installed; Sentry disabled")
        return

    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        integrations=[FastApiIntegration(), SqlalchemyIntegration(), CeleryIntegration()],
    )
    logger.info("Sentry initialised", extra={"environment": environment})


def _setup_otel(endpoint: str, service_name: str, insecure: bool, app: Any) -> Any | None:
    if not endpoint:
        return None
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from backend.db.session import engine

        resource = Resource(attributes={SERVICE_NAME: service_name})
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure))
        )
        trace.set_tracer_provider(tracer_provider)

        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=insecure)
        )
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

        if app is not None:
            FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        HTTPXClientInstrumentor().instrument()
        RedisInstrumentor().instrument()
        logger.info("OpenTelemetry initialised", extra={"endpoint": endpoint})
        return metrics.get_meter("content_generator.domain")
    except ImportError:
        logger.warning("opentelemetry packages not installed; OTel disabled")
        return None

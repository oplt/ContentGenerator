from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def setup_telemetry(app=None) -> None:  # type: ignore[type-arg]
    from backend.core.config import settings

    _setup_sentry(
        settings.SENTRY_DSN,
        settings.APP_ENV,
        settings.SENTRY_TRACES_SAMPLE_RATE,
    )
    _setup_otel(
        settings.OTLP_ENDPOINT,
        settings.OTEL_SERVICE_NAME,
        settings.OTLP_INSECURE,
        app,
    )


def _setup_sentry(dsn: str, environment: str, traces_sample_rate: float) -> None:
    if not dsn:
        return
    try:
        import sentry_sdk
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
    except ImportError:
        logger.warning("sentry-sdk not installed; Sentry disabled")


def _setup_otel(endpoint: str, service_name: str, insecure: bool, app) -> None:  # type: ignore[type-arg]
    if not endpoint:
        return
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
    except ImportError:
        logger.warning("opentelemetry packages not installed; OTel disabled")

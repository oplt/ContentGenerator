from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.middleware.correlation_id import CorrelationIdMiddleware
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.api.router import api_router
from backend.api.v1.health import MetricsResponse, metrics as health_metrics
from backend.core.bootstrap import bootstrap_application
from backend.core.cache import redis_cache
from backend.core.config import settings
from backend.core.error_handler import register_exception_handlers
from backend.core.logging import setup_logging
from backend.core.storage import object_storage
from backend.core.telemetry import setup_telemetry
from backend.db import model_registry  # noqa: F401
from backend.db.session import SessionLocal, engine

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    setup_telemetry(app)

    from backend.db.schema_revision import SchemaRevisionError, assert_schema_at_head

    try:
        assert_schema_at_head(role="api")
    except SchemaRevisionError as exc:
        raise RuntimeError(str(exc)) from exc

    # Initialize Redis connection
    await redis_cache.connect()

    # Ensure storage bucket exists
    await object_storage.ensure_bucket()

    # Run bootstrap
    async with SessionLocal() as db:
        await bootstrap_application(db)

    yield

    # Shutdown
    from backend.core.http import close_http_client

    await close_http_client()
    await redis_cache.close()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)


@app.get("/metrics", response_model=MetricsResponse, include_in_schema=False)
async def root_metrics() -> MetricsResponse:
    """Compatibility endpoint for scrapers configured with the root path."""
    return await health_metrics()

app.add_middleware(RequestLoggingMiddleware)
# CorrelationId must wrap request logging so the ID exists for the full
# request_complete / request_failed log and contextvars are cleared only after.
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.middleware.correlation_id import CorrelationIdMiddleware
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.api.router import api_router
from backend.core.bootstrap import bootstrap_application
from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.error_handler import register_exception_handlers
from backend.core.logging import setup_logging
from backend.core.storage import object_storage
from backend.core.telemetry import setup_telemetry
from backend.db import model_registry  # noqa: F401
from backend.db.session import SessionLocal, engine

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry(app)
    await object_storage.ensure_bucket()
    async with SessionLocal() as db:
        await bootstrap_application(db)
    yield
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)

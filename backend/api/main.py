from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .middleware.correlation_id import CorrelationIdMiddleware
from .middleware.request_logging import RequestLoggingMiddleware
from .router import api_router
from .v1.health import health_router
from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.error_handler import register_exception_handlers
from backend.core.logging import setup_logging
from backend.core.storage import object_storage
from backend.core.telemetry import setup_telemetry
from backend.db.session import SessionLocal, engine
from backend.modules.platform.service import PlatformService

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry(app)
    await object_storage.ensure_bucket()
    async with SessionLocal() as db:
        platform_service = PlatformService(db)
        await platform_service.ensure_defaults()
    yield
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)
app.include_router(health_router)

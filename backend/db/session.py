"""
Database engine, session factory, and pool observability.

Transaction ownership (T2.3)
----------------------------
* Repositories / domain services: ``flush()`` only (persist identity, stay uncommitted).
* Entrypoints commit/roll back once:
  - HTTP: ``api.deps.db.get_db``
  - Workers: ``workers.runtime.run_async_task`` / ``run_async_task_simple``
* Deliberate split-phase commits (e.g. publishing claim → provider I/O → finalize)
  remain inside those workflows and must document why.
* Durable failure ledgers before an HTTP error (e.g. ingestion fetch_run) may
  ``commit()`` explicitly, then re-raise; entrypoint rollback is then a no-op.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from backend.core.config import settings
from backend.core.db_observability import attach_db_observability, reset_db_observability_state
from backend.core.domain_metrics import domain_metrics

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_pool_listeners_attached = False

# Process-local counters for pool observability (tests + logs).
_pool_stats: dict[str, int] = {
    "connect": 0,
    "checkout": 0,
    "checkin": 0,
    "invalidate": 0,
}


def get_pool_stats() -> dict[str, int]:
    """Return a copy of pool event counters for this process."""
    return dict(_pool_stats)


def reset_pool_stats() -> None:
    for key in _pool_stats:
        _pool_stats[key] = 0


def _engine_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "echo": settings.SQL_ECHO,
        "pool_pre_ping": True,
    }
    if settings.DB_POOL_USE_NULL:
        kwargs["poolclass"] = NullPool
        return kwargs

    kwargs.update(
        {
            "pool_size": settings.effective_db_pool_size,
            "max_overflow": settings.effective_db_pool_max_overflow,
            "pool_timeout": settings.DB_POOL_TIMEOUT_SECONDS,
            "pool_recycle": settings.DB_POOL_RECYCLE_SECONDS,
        }
    )
    return kwargs


def _attach_pool_listeners(engine: AsyncEngine) -> None:
    global _pool_listeners_attached
    if _pool_listeners_attached:
        return

    sync_engine = engine.sync_engine
    attach_db_observability(sync_engine)

    if not settings.DB_POOL_USE_NULL:

        @event.listens_for(sync_engine, "connect")
        def _on_connect(dbapi_connection: Any, connection_record: Any) -> None:  # noqa: ARG001
            _pool_stats["connect"] += 1
            domain_metrics.record_db_pool(event="connect")

        @event.listens_for(sync_engine, "checkout")
        def _on_checkout(
            dbapi_connection: Any,  # noqa: ARG001
            connection_record: Any,  # noqa: ARG001
            connection_proxy: Any,  # noqa: ARG001
        ) -> None:
            _pool_stats["checkout"] += 1
            domain_metrics.record_db_pool(event="checkout")

        @event.listens_for(sync_engine, "checkin")
        def _on_checkin(dbapi_connection: Any, connection_record: Any) -> None:  # noqa: ARG001
            _pool_stats["checkin"] += 1
            domain_metrics.record_db_pool(event="checkin")

        @event.listens_for(sync_engine, "invalidate")
        def _on_invalidate(
            dbapi_connection: Any,  # noqa: ARG001
            connection_record: Any,  # noqa: ARG001
            exception: BaseException | None,  # noqa: ARG001
        ) -> None:
            _pool_stats["invalidate"] += 1
            domain_metrics.record_db_pool(event="invalidate")

        logger.info(
            "db_pool_configured role=%s size=%s overflow=%s timeout=%s recycle=%s max_per_process=%s",
            settings.DB_POOL_PROCESS_ROLE,
            settings.effective_db_pool_size,
            settings.effective_db_pool_max_overflow,
            settings.DB_POOL_TIMEOUT_SECONDS,
            settings.DB_POOL_RECYCLE_SECONDS,
            settings.db_pool_max_connections_per_process,
        )

    _pool_listeners_attached = True


def get_engine() -> AsyncEngine:
    global _engine

    if _engine is None:
        _engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs())
        _attach_pool_listeners(_engine)

    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker

    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _sessionmaker


class _SessionLocalProxy:
    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        return get_sessionmaker()(*args, **kwargs)


class _EngineProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_engine(), name)


SessionLocal = _SessionLocalProxy()
engine = _EngineProxy()


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a session; commit on success, rollback on error (entrypoint ownership)."""
    started = time.perf_counter()
    outcome = "success"
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            outcome = "failure"
            await session.rollback()
            raise
        finally:
            domain_metrics.record_db_tx(
                outcome=outcome,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )


async def dispose_engine() -> None:
    global _engine, _sessionmaker, _pool_listeners_attached

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _sessionmaker = None
    _pool_listeners_attached = False
    reset_db_observability_state()

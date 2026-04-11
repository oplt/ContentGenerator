from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from backend.core.config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine

    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.SQL_ECHO,
            pool_pre_ping=True,
            poolclass=NullPool,
        )

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
    def __call__(self, *args: Any, **kwargs: Any):
        return get_sessionmaker()(*args, **kwargs)


class _EngineProxy:
    def __getattr__(self, name: str):
        return getattr(get_engine(), name)


SessionLocal = _SessionLocalProxy()
engine = _EngineProxy()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _sessionmaker = None
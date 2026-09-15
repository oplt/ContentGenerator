"""Explicit transaction ownership helpers (T2.3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import SessionLocal


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """
    Entrypoint-owned unit of work: commit on success, rollback on error.

    Use from scripts/workers that are not going through ``get_db`` /
    ``run_async_task``. Domain code should only ``flush()``.
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

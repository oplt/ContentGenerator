from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import SessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Request-scoped session with entrypoint transaction ownership.

    Success → commit once. Failure → rollback. Services should flush;
    mid-request ``commit()`` only for deliberate split-phase workflows
    (publishing) or durable failure ledgers before re-raise.
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

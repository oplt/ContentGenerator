"""
Request-scoped session with entrypoint transaction ownership.

Success → commit once. Failure → rollback. Services should flush;
mid-request ``commit()`` only for deliberate split-phase workflows
(publishing) or durable failure ledgers before re-raise.
"""

from collections.abc import AsyncGenerator
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.domain_metrics import domain_metrics
from backend.db.session import SessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    started = perf_counter()
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
                duration_ms=(perf_counter() - started) * 1000.0,
            )

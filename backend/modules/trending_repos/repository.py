from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.trending_repos.models import TrendingRepo


class TrendingReposRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_period_and_date(
        self,
        tenant_id: uuid.UUID,
        period: str,
        snapshot_date: date,
    ) -> list[TrendingRepo]:
        stmt = (
            select(TrendingRepo)
            .where(
                TrendingRepo.tenant_id == tenant_id,
                TrendingRepo.period == period,
                TrendingRepo.snapshot_date == snapshot_date,
            )
            .order_by(TrendingRepo.rank)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_period(
        self,
        tenant_id: uuid.UUID,
        period: str,
    ) -> list[TrendingRepo]:
        """Get the most recent snapshot for a period."""
        # Find the latest snapshot date for this period
        latest_date_stmt = (
            select(TrendingRepo.snapshot_date)
            .where(
                TrendingRepo.tenant_id == tenant_id,
                TrendingRepo.period == period,
            )
            .order_by(TrendingRepo.snapshot_date.desc())
            .limit(1)
        )
        date_result = await self.db.execute(latest_date_stmt)
        latest = date_result.scalar_one_or_none()
        if latest is None:
            return []
        return await self.get_by_period_and_date(tenant_id, period, latest)

    async def upsert_snapshot(
        self,
        tenant_id: uuid.UUID,
        period: str,
        snapshot_date: date,
        repos: list[dict],
    ) -> list[TrendingRepo]:
        """Delete existing snapshot for this period+date and insert fresh rows."""
        await self.db.execute(
            delete(TrendingRepo).where(
                TrendingRepo.tenant_id == tenant_id,
                TrendingRepo.period == period,
                TrendingRepo.snapshot_date == snapshot_date,
            )
        )
        records = []
        for rank, repo_data in enumerate(repos, start=1):
            record = TrendingRepo(
                tenant_id=tenant_id,
                period=period,
                snapshot_date=snapshot_date,
                rank=rank,
                **repo_data,
            )
            self.db.add(record)
            records.append(record)
        await self.db.flush()
        return records

    async def get_by_id(
        self, tenant_id: uuid.UUID, repo_id: uuid.UUID
    ) -> TrendingRepo | None:
        stmt = select(TrendingRepo).where(
            TrendingRepo.id == repo_id,
            TrendingRepo.tenant_id == tenant_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save(self, repo: TrendingRepo) -> TrendingRepo:
        self.db.add(repo)
        await self.db.flush()
        return repo

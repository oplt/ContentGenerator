"""Editorial brief service facade — generation, lifecycle, and Telegram gate."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_strategy.repository import ContentStrategyRepository
from backend.modules.editorial_briefs.brief_generation import BriefGenerationMixin
from backend.modules.editorial_briefs.brief_rewrite import BriefRewriteMixin
from backend.modules.editorial_briefs.brief_telegram import BriefTelegramMixin
from backend.modules.editorial_briefs.models import BriefStatus, EditorialBrief
from backend.modules.editorial_briefs.repository import EditorialBriefRepository
from backend.modules.inference.providers import get_llm_provider
from backend.modules.story_intelligence.models import TrendWorkflowState
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository


class EditorialBriefService(BriefGenerationMixin, BriefRewriteMixin, BriefTelegramMixin):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = EditorialBriefRepository(db)
        self.story_repo = StoryIntelligenceRepository(db)
        self.strategy_repo = ContentStrategyRepository(db)
        self.llm = get_llm_provider()

    async def approve_brief(
        self,
        tenant_id: UUID,
        brief_id: UUID,
        operator_note: str | None,
        actor_user_id: UUID | None,
    ) -> EditorialBrief:
        brief = await self._get_or_404(tenant_id, brief_id)
        if brief.status != BriefStatus.READY.value:
            raise HTTPException(
                status_code=409, detail=f"Brief is in status '{brief.status}', expected 'ready'"
            )
        cluster = await self.story_repo.get_cluster(tenant_id, brief.story_cluster_id)
        if cluster:
            await self._resolve_brand_constraints(tenant_id, brief.brand_profile_id, cluster.primary_topic)
        brief.status = BriefStatus.APPROVED.value
        if cluster:
            cluster.workflow_state = TrendWorkflowState.APPROVED_TOPIC.value
        brief.operator_note = operator_note
        brief.approved_by_user_id = actor_user_id
        brief.actioned_at = datetime.now(timezone.utc)
        await self.db.flush()
        return brief

    async def reject_brief(
        self,
        tenant_id: UUID,
        brief_id: UUID,
        operator_note: str,
        actor_user_id: UUID | None,
    ) -> EditorialBrief:
        brief = await self._get_or_404(tenant_id, brief_id)
        if brief.status not in (BriefStatus.READY.value, BriefStatus.APPROVED.value):
            raise HTTPException(
                status_code=409, detail=f"Brief is in status '{brief.status}', cannot reject"
            )
        brief.status = BriefStatus.REJECTED.value
        cluster = await self.story_repo.get_cluster(tenant_id, brief.story_cluster_id)
        if cluster:
            cluster.workflow_state = TrendWorkflowState.REJECTED.value
        brief.operator_note = operator_note
        brief.approved_by_user_id = actor_user_id
        brief.actioned_at = datetime.now(timezone.utc)
        await self.db.flush()
        return brief

    async def expire_stale_briefs(self, tenant_id: UUID) -> int:
        """Mark READY briefs past their expires_at as EXPIRED. Called by Celery beat."""
        now = datetime.now(timezone.utc)
        briefs = await self.repo.list_by_tenant(tenant_id, status=BriefStatus.READY.value)
        count = 0
        for brief in briefs:
            if brief.expires_at and brief.expires_at < now:
                brief.status = BriefStatus.EXPIRED.value
                cluster = await self.story_repo.get_cluster(tenant_id, brief.story_cluster_id)
                if cluster:
                    cluster.workflow_state = TrendWorkflowState.EXPIRED.value
                count += 1
        if count:
            await self.db.flush()
        return count

    async def get_brief(self, tenant_id: UUID, brief_id: UUID) -> EditorialBrief:
        return await self._get_or_404(tenant_id, brief_id)

    async def list_briefs(
        self, tenant_id: UUID, status: str | None = None, limit: int = 50
    ) -> list[EditorialBrief]:
        return await self.repo.list_by_tenant(tenant_id, status=status, limit=limit)

    async def _get_or_404(self, tenant_id: UUID, brief_id: UUID) -> EditorialBrief:
        brief = await self.repo.get(tenant_id, brief_id)
        if not brief:
            raise HTTPException(status_code=404, detail="Editorial brief not found")
        return brief

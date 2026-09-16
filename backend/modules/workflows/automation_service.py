"""Automation create/list/update for Phase 13 UI (+ Phase 17 security)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_strategy.models import Brand
from backend.modules.workflows.automation_repository import AutomationRepository
from backend.modules.workflows.automation_schemas import (
    AutomationCreateRequest,
    AutomationResponse,
    AutomationTargetResponse,
    AutomationUpdateRequest,
    BrandOptionResponse,
)
from backend.modules.workflows.models import Automation, AutomationTriggerType
from backend.modules.workflows.repository import WorkflowRepository
from backend.modules.workflows.scheduler import AutomationScheduler
from backend.modules.workflows.security import (
    authorize_social_account_ids,
    sanitize_mapping,
)


class AutomationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AutomationRepository(db)
        self.workflows = WorkflowRepository(db)
        self.scheduler = AutomationScheduler(db)
        self.audit = AuditService(db)

    async def list_brands(self, tenant_id: UUID) -> list[BrandOptionResponse]:
        result = await self.db.execute(
            select(Brand).where(Brand.tenant_id == tenant_id, Brand.deleted_at.is_(None))
        )
        return [
            BrandOptionResponse(id=row.id, name=row.name, niche=row.niche)
            for row in result.scalars().all()
        ]

    async def list_automations(self, tenant_id: UUID) -> list[AutomationResponse]:
        rows = await self.repo.list_automations(tenant_id)
        return [await self._to_response(tenant_id, row) for row in rows]

    async def get_automation(
        self, tenant_id: UUID, automation_id: UUID
    ) -> AutomationResponse | None:
        row = await self.repo.get_automation(tenant_id, automation_id)
        if row is None:
            return None
        return await self._to_response(tenant_id, row)

    async def create_automation(
        self,
        tenant_id: UUID,
        payload: AutomationCreateRequest,
        *,
        actor_user_id: UUID | None = None,
    ) -> AutomationResponse:
        definition = await self.workflows.get_definition(
            tenant_id, payload.workflow_definition_id
        )
        if definition is None:
            raise HTTPException(status_code=404, detail="Workflow definition not found")
        version_id = payload.workflow_version_id or definition.current_version_id
        if version_id is None:
            raise HTTPException(status_code=400, detail="Workflow has no published version")
        version = await self.workflows.get_version(tenant_id, version_id)
        if version is None or version.published_at is None:
            raise HTTPException(status_code=400, detail="Workflow version is not published")
        brand_id = payload.brand_id or await self._default_brand_id(tenant_id)
        if brand_id is None:
            raise HTTPException(status_code=400, detail="No brand available for automation")

        await authorize_social_account_ids(
            self.db, tenant_id=tenant_id, social_account_ids=list(payload.social_account_ids)
        )
        automation = Automation(
            tenant_id=tenant_id,
            workflow_definition_id=payload.workflow_definition_id,
            workflow_version_id=version_id,
            brand_id=brand_id,
            name=payload.name.strip(),
            enabled=payload.enabled,
            trigger_type=payload.trigger_type,
            trigger_config=sanitize_mapping(payload.trigger_config),
            timezone=payload.timezone,
            settings=sanitize_mapping(payload.settings),
        )
        await self.repo.add_automation(automation)
        if payload.social_account_ids:
            await self.repo.replace_targets(
                tenant_id=tenant_id,
                automation_id=automation.id,
                social_account_ids=list(payload.social_account_ids),
            )
        if automation.trigger_type == AutomationTriggerType.SCHEDULE.value:
            await self.scheduler.ensure_next_run_at(automation)
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="automations.created",
            entity_type="automation",
            entity_id=str(automation.id),
            message="Automation created",
            payload={
                "enabled": automation.enabled,
                "target_count": len(payload.social_account_ids),
                "workflow_definition_id": str(payload.workflow_definition_id),
            },
            outcome="success",
        )
        return await self._to_response(tenant_id, automation)

    async def update_automation(
        self,
        tenant_id: UUID,
        automation_id: UUID,
        payload: AutomationUpdateRequest,
        *,
        actor_user_id: UUID | None = None,
    ) -> AutomationResponse:
        automation = await self.repo.get_automation(tenant_id, automation_id)
        if automation is None:
            raise HTTPException(status_code=404, detail="Automation not found")
        prev_enabled = automation.enabled
        if payload.name is not None:
            automation.name = payload.name.strip()
        if payload.workflow_version_id is not None:
            version = await self.workflows.get_version(tenant_id, payload.workflow_version_id)
            if version is None or version.published_at is None:
                raise HTTPException(status_code=400, detail="Workflow version is not published")
            automation.workflow_version_id = payload.workflow_version_id
        if payload.enabled is not None:
            automation.enabled = payload.enabled
        if payload.trigger_type is not None:
            automation.trigger_type = payload.trigger_type
        if payload.trigger_config is not None:
            automation.trigger_config = sanitize_mapping(payload.trigger_config)
        if payload.timezone is not None:
            automation.timezone = payload.timezone
        if payload.settings is not None:
            automation.settings = sanitize_mapping(payload.settings)
        if payload.social_account_ids is not None:
            await authorize_social_account_ids(
                self.db,
                tenant_id=tenant_id,
                social_account_ids=list(payload.social_account_ids),
            )
            await self.repo.replace_targets(
                tenant_id=tenant_id,
                automation_id=automation.id,
                social_account_ids=list(payload.social_account_ids),
            )
            await self.audit.record(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="automations.targets_changed",
                entity_type="automation",
                entity_id=str(automation.id),
                message="Automation targets updated",
                payload={"target_count": len(payload.social_account_ids)},
                outcome="success",
            )
        await self.db.flush()
        if automation.trigger_type == AutomationTriggerType.SCHEDULE.value:
            await self.scheduler.ensure_next_run_at(automation)
        elif not automation.enabled:
            automation.next_run_at = None
        if payload.enabled is not None and payload.enabled != prev_enabled:
            await self.audit.record(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="automations.enabled_changed",
                entity_type="automation",
                entity_id=str(automation.id),
                message="Automation enabled flag changed",
                payload={"enabled": automation.enabled, "previous": prev_enabled},
                outcome="success",
            )
        return await self._to_response(tenant_id, automation)

    async def _default_brand_id(self, tenant_id: UUID) -> UUID | None:
        brands = await self.list_brands(tenant_id)
        return brands[0].id if brands else None

    async def _to_response(self, tenant_id: UUID, row: Automation) -> AutomationResponse:
        targets = await self.repo.list_targets(tenant_id, row.id)
        return AutomationResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            workflow_definition_id=row.workflow_definition_id,
            workflow_version_id=row.workflow_version_id,
            brand_id=row.brand_id,
            name=row.name,
            enabled=row.enabled,
            trigger_type=row.trigger_type,
            trigger_config=sanitize_mapping(row.trigger_config),
            timezone=row.timezone,
            next_run_at=row.next_run_at,
            last_run_at=row.last_run_at,
            settings=sanitize_mapping(row.settings),
            created_at=row.created_at,
            updated_at=row.updated_at,
            targets=[
                AutomationTargetResponse(
                    id=t.id,
                    social_account_id=t.social_account_id,
                    enabled=t.enabled,
                    overrides_json=sanitize_mapping(t.overrides_json),
                )
                for t in targets
            ],
        )

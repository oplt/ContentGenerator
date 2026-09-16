"""Automation create/list/update for Phase 13 UI (+ Phase 6 integrity / Phase 17 security)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_strategy.models import Brand
from backend.modules.workflows.automation_integrity import (
    authorize_brand_linked_accounts,
    require_active_brand,
    require_version_for_definition,
)
from backend.modules.workflows.automation_repository import AutomationRepository
from backend.modules.workflows.automation_schemas import (
    AutomationCreateRequest,
    AutomationResponse,
    AutomationTargetResponse,
    AutomationUpdateRequest,
    BrandOptionResponse,
)
from backend.modules.workflows.models import Automation
from backend.modules.workflows.repository import WorkflowRepository
from backend.modules.workflows.scheduler import AutomationScheduler
from backend.modules.workflows.security import sanitize_mapping
from backend.modules.workflows.webhook_trigger_config import normalize_webhook_trigger_config


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
        await require_version_for_definition(
            self.db,
            tenant_id=tenant_id,
            workflow_definition_id=payload.workflow_definition_id,
            workflow_version_id=version_id,
            require_published=True,
        )

        brand_id = payload.brand_id or await self._default_brand_id(tenant_id)
        if brand_id is None:
            raise HTTPException(status_code=400, detail="No brand available for automation")
        await require_active_brand(self.db, tenant_id=tenant_id, brand_id=brand_id)

        await authorize_brand_linked_accounts(
            self.db,
            tenant_id=tenant_id,
            brand_id=brand_id,
            social_account_ids=list(payload.social_account_ids),
            allow_unlinked_targets=bool(payload.allow_unlinked_targets),
        )
        trigger_config = sanitize_mapping(payload.trigger_config)
        webhook_endpoint_id: str | None = None
        if payload.trigger_type in {"webhook", "event"}:
            try:
                trigger_config = normalize_webhook_trigger_config(trigger_config)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            webhook_endpoint_id = str(trigger_config["endpoint_id"])
        automation = Automation(
            tenant_id=tenant_id,
            workflow_definition_id=payload.workflow_definition_id,
            workflow_version_id=version_id,
            brand_id=brand_id,
            name=payload.name.strip(),
            enabled=payload.enabled,
            trigger_type=payload.trigger_type,
            trigger_config=trigger_config,
            timezone=payload.timezone,
            settings=sanitize_mapping(payload.settings),
            webhook_endpoint_id=webhook_endpoint_id,
        )
        await self.repo.add_automation(automation)
        if payload.social_account_ids:
            await self.repo.replace_targets(
                tenant_id=tenant_id,
                automation_id=automation.id,
                social_account_ids=list(payload.social_account_ids),
            )
        await self.scheduler.sync_schedule_state(automation, force_recompute=True)
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
                "allow_unlinked_targets": bool(payload.allow_unlinked_targets),
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
        schedule_dirty = any(
            (
                payload.enabled is not None,
                payload.trigger_type is not None,
                payload.trigger_config is not None,
                payload.timezone is not None,
            )
        )
        if payload.name is not None:
            automation.name = payload.name.strip()
        if payload.workflow_version_id is not None:
            await require_version_for_definition(
                self.db,
                tenant_id=tenant_id,
                workflow_definition_id=automation.workflow_definition_id,
                workflow_version_id=payload.workflow_version_id,
                require_published=True,
            )
            automation.workflow_version_id = payload.workflow_version_id
        if payload.brand_id is not None:
            await require_active_brand(
                self.db, tenant_id=tenant_id, brand_id=payload.brand_id
            )
            automation.brand_id = payload.brand_id
        if payload.enabled is not None:
            automation.enabled = payload.enabled
        if payload.trigger_type is not None:
            automation.trigger_type = payload.trigger_type
        if payload.trigger_config is not None or (
            payload.trigger_type is not None and payload.trigger_type in {"webhook", "event"}
        ):
            raw_cfg = (
                sanitize_mapping(payload.trigger_config)
                if payload.trigger_config is not None
                else dict(automation.trigger_config or {})
            )
            if automation.trigger_type in {"webhook", "event"}:
                try:
                    raw_cfg = normalize_webhook_trigger_config(
                        raw_cfg,
                        existing_endpoint_id=automation.webhook_endpoint_id,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                automation.webhook_endpoint_id = str(raw_cfg["endpoint_id"])
            else:
                automation.webhook_endpoint_id = None
            automation.trigger_config = raw_cfg
        elif payload.trigger_type is not None and payload.trigger_type not in {
            "webhook",
            "event",
        }:
            automation.webhook_endpoint_id = None
        if payload.timezone is not None:
            automation.timezone = payload.timezone
        if payload.settings is not None:
            automation.settings = sanitize_mapping(payload.settings)
        if payload.social_account_ids is not None or payload.brand_id is not None:
            # Re-validate linkage when brand or targets change.
            target_ids = (
                list(payload.social_account_ids)
                if payload.social_account_ids is not None
                else [t.social_account_id for t in await self.repo.list_targets(tenant_id, automation.id)]
            )
            await authorize_brand_linked_accounts(
                self.db,
                tenant_id=tenant_id,
                brand_id=automation.brand_id,
                social_account_ids=target_ids,
                allow_unlinked_targets=bool(payload.allow_unlinked_targets),
            )
        if payload.social_account_ids is not None:
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
                payload={
                    "target_count": len(payload.social_account_ids),
                    "allow_unlinked_targets": bool(payload.allow_unlinked_targets),
                },
                outcome="success",
            )
        await self.db.flush()
        if schedule_dirty:
            await self.scheduler.sync_schedule_state(automation, force_recompute=True)
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

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.approvals.models import ApprovalMessage, ApprovalRequest, ApprovalStatus, WebhookInbox


class ApprovalRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        self.db.add(request)
        await self.db.flush()
        return request

    async def create_message(self, message: ApprovalMessage) -> ApprovalMessage:
        self.db.add(message)
        await self.db.flush()
        return message

    async def create_webhook(self, inbox: WebhookInbox) -> WebhookInbox:
        self.db.add(inbox)
        await self.db.flush()
        return inbox

    async def list_requests(self, tenant_id: UUID, limit: int = 50) -> list[ApprovalRequest]:
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.tenant_id == tenant_id)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_requests_by_status(
        self,
        tenant_id: UUID,
        statuses: list[str],
        limit: int = 100,
    ) -> list[ApprovalRequest]:
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.tenant_id == tenant_id, ApprovalRequest.status.in_(statuses))
            .order_by(ApprovalRequest.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_request(self, tenant_id: UUID, request_id: UUID) -> ApprovalRequest | None:
        result = await self.db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.id == request_id,
                ApprovalRequest.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_request_by_id(self, request_id: UUID) -> ApprovalRequest | None:
        result = await self.db.execute(select(ApprovalRequest).where(ApprovalRequest.id == request_id))
        return result.scalar_one_or_none()

    async def list_messages(self, request_id: UUID) -> list[ApprovalMessage]:
        result = await self.db.execute(
            select(ApprovalMessage)
            .where(ApprovalMessage.approval_request_id == request_id)
            .order_by(ApprovalMessage.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_webhook_by_dedupe_key(self, dedupe_key: str) -> WebhookInbox | None:
        result = await self.db.execute(
            select(WebhookInbox).where(WebhookInbox.dedupe_key == dedupe_key)
        )
        return result.scalar_one_or_none()

    async def get_pending_webhook(self, inbox_id: UUID) -> WebhookInbox | None:
        result = await self.db.execute(
            select(WebhookInbox).where(WebhookInbox.id == inbox_id)
        )
        return result.scalar_one_or_none()

    async def list_pending_inbox(self, limit: int = 50) -> list[WebhookInbox]:
        result = await self.db.execute(
            select(WebhookInbox)
            .where(WebhookInbox.status == "received")
            .order_by(WebhookInbox.received_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_expired_pending_requests(self) -> list[ApprovalRequest]:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
                ApprovalRequest.expires_at <= now,
            )
        )
        return list(result.scalars().all())

    async def get_request_for_content_job(self, content_job_id: UUID) -> ApprovalRequest | None:
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.content_job_id == content_job_id)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_request_for_related_entity(
        self,
        tenant_id: UUID,
        related_entity_type: str,
        related_entity_id: str,
        approval_type: str,
    ) -> ApprovalRequest | None:
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.tenant_id == tenant_id,
                ApprovalRequest.related_entity_type == related_entity_type,
                ApprovalRequest.related_entity_id == related_entity_id,
                ApprovalRequest.approval_type == approval_type,
            )
            .order_by(ApprovalRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

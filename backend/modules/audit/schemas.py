from __future__ import annotations

from uuid import UUID

from backend.modules.shared.schemas import ORMModel


class AuditLogResponse(ORMModel):
    id: UUID
    tenant_id: UUID | None
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    correlation_id: str | None
    message: str
    payload: dict[str, str]

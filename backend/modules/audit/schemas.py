from __future__ import annotations

from typing import Any
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
    # Stored payloads use mixed JSON values (bool/int/nested), not string-only maps.
    payload: dict[str, Any]

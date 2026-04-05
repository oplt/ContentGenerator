from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from uuid import UUID


def encode_cursor(created_at: datetime, entity_id: UUID) -> str:
    payload = f"{created_at.isoformat()}|{entity_id}"
    return urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str | None) -> tuple[datetime, UUID] | None:
    if not cursor:
        return None
    decoded = urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
    created_at_raw, entity_id_raw = decoded.split("|", maxsplit=1)
    return datetime.fromisoformat(created_at_raw), UUID(entity_id_raw)

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ArticleCursor:
    created_at: datetime
    article_id: UUID


def encode_article_cursor(*, created_at: datetime, article_id: UUID) -> str:
    payload = json.dumps(
        {"created_at": created_at.astimezone(timezone.utc).isoformat(), "id": str(article_id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_article_cursor(value: str) -> ArticleCursor:
    try:
        payload = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        decoded = json.loads(payload)
        created_at = datetime.fromisoformat(decoded["created_at"])
        article_id = UUID(decoded["id"])
        if created_at.utcoffset() is None:
            raise ValueError("cursor timestamp must include a timezone")
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("Invalid article cursor") from exc
    return ArticleCursor(created_at=created_at, article_id=article_id)

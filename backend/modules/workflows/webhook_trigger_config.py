"""Automation webhook / event trigger_config (Phase 17).

Secrets are reference IDs only — never raw values in graph_json or trigger_config.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from pydantic import BaseModel, Field, field_validator

_ENDPOINT_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")
_REF_RE = re.compile(r"^[a-zA-Z0-9_.:/-]{1,256}$")


class WebhookTriggerConfig(BaseModel):
    """Normalized automation.trigger_config when trigger_type is webhook|event."""

    endpoint_id: str = Field(min_length=8, max_length=64)
    signing_secret_ref: str = Field(min_length=1, max_length=256)
    provider: str = Field(default="generic_hmac", pattern="^(generic_hmac|hmac_sha256)$")
    signature_header: str = Field(default="X-SignalForge-Signature", max_length=128)
    timestamp_header: str = Field(default="X-SignalForge-Timestamp", max_length=128)
    idempotency_header: str = Field(default="X-Idempotency-Key", max_length=128)
    max_skew_seconds: int = Field(default=300, ge=30, le=3600)
    require_timestamp: bool = True

    @field_validator("endpoint_id")
    @classmethod
    def _endpoint(cls, value: str) -> str:
        raw = value.strip()
        if not _ENDPOINT_RE.match(raw):
            raise ValueError("endpoint_id must be 8–64 chars [A-Za-z0-9_-]")
        return raw

    @field_validator("signing_secret_ref")
    @classmethod
    def _secret_ref(cls, value: str) -> str:
        raw = value.strip()
        lowered = raw.lower()
        if any(tok in lowered for tok in ("password", "secret=", "token=")):
            raise ValueError("signing_secret_ref must be a reference id, not a raw secret")
        if not _REF_RE.match(raw):
            raise ValueError("invalid signing_secret_ref")
        return raw


def new_endpoint_id() -> str:
    return secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:24]


def normalize_webhook_trigger_config(
    raw: dict[str, Any] | None,
    *,
    existing_endpoint_id: str | None = None,
) -> dict[str, Any]:
    """Validate and return a sanitized trigger_config dict (refs only)."""
    payload = dict(raw or {})
    if not payload.get("endpoint_id"):
        payload["endpoint_id"] = existing_endpoint_id or new_endpoint_id()
    if "signing_secret_ref" not in payload or not str(payload.get("signing_secret_ref") or "").strip():
        raise ValueError("signing_secret_ref is required for webhook triggers")
    # Strip any accidental raw secret fields.
    for banned in ("signing_secret", "secret", "webhook_secret", "hmac_secret"):
        payload.pop(banned, None)
    cfg = WebhookTriggerConfig.model_validate(payload)
    return cfg.model_dump()


def parse_webhook_trigger_config(raw: dict[str, Any] | None) -> WebhookTriggerConfig:
    return WebhookTriggerConfig.model_validate(dict(raw or {}))

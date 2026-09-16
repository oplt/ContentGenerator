"""HMAC verify + replay helpers for workflow webhook ingress (Phase 17)."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


def parse_timestamp(raw: str | None) -> int | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def verify_generic_hmac(
    *,
    secret: str,
    body: bytes,
    signature_header: str | None,
    timestamp: int | None,
    max_skew_seconds: int,
    now: int | None = None,
    require_timestamp: bool = True,
) -> bool:
    """Verify ``sha256=<hex>`` over ``{timestamp}.{body}`` (or body alone if allowed)."""
    if not secret or not signature_header:
        return False
    header = signature_header.strip()
    provided = header
    if header.lower().startswith("sha256="):
        provided = header.split("=", 1)[1].strip()
    elif "," in header and "v1=" in header:
        # Stripe-like: t=...,v1=...
        parts = dict(
            part.split("=", 1) for part in header.split(",") if "=" in part
        )
        provided = (parts.get("v1") or "").strip()
        if timestamp is None and parts.get("t"):
            timestamp = parse_timestamp(parts.get("t"))

    clock = int(now if now is not None else time.time())
    if require_timestamp:
        if timestamp is None:
            return False
        if abs(clock - timestamp) > max_skew_seconds:
            return False
        signed = f"{timestamp}.".encode("utf-8") + body
    else:
        signed = body

    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


def stable_event_id(
    *,
    idempotency_key: str | None,
    body: bytes,
) -> str:
    if idempotency_key and idempotency_key.strip():
        return hashlib.sha256(idempotency_key.strip().encode("utf-8")).hexdigest()
    return hashlib.sha256(body).hexdigest()


def sanitize_trigger_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from backend.modules.workflows.config_merge import strip_secrets

    return dict(strip_secrets(payload))

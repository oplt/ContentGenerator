"""Redact sensitive values from operator-facing workflow payloads."""

from __future__ import annotations

from typing import Any

_REDACTED = "[redacted]"

_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "access_key",
)

_EXACT_SENSITIVE = frozenset(
    {
        "resume_token",
        "claim_token",
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "private_key",
        "access_key",
        "refresh_token",
        "oauth_token",
        "webhook_secret",
        "provider_secret",
    }
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    if lowered in _EXACT_SENSITIVE:
        return True
    return any(frag in lowered for frag in _SENSITIVE_KEY_FRAGMENTS)


def redact_value(value: Any) -> Any:
    """Deep-copy redact nested dict/list structures for API inspection."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                out[str(key)] = _REDACTED
            else:
                out[str(key)] = redact_value(item)
        return out
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    return value

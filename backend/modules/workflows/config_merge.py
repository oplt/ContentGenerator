"""Deep-merge helpers for workflow config precedence (Phase 8)."""

from __future__ import annotations

from typing import Any

_SECRET_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "refresh",
    "oauth",
    "bearer",
)

# Account-oriented aliases → node config fields.
_KEY_ALIASES = {
    "max_length": "max_tokens",
}


def is_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(frag in lowered for frag in _SECRET_FRAGMENTS)


def strip_secrets(value: Any) -> Any:
    """Recursively drop secret-looking keys. Never snapshot credentials."""
    if isinstance(value, dict):
        return {
            str(k): strip_secrets(v)
            for k, v in value.items()
            if not is_secret_key(str(k))
        }
    if isinstance(value, list):
        return [strip_secrets(item) for item in value]
    return value


def as_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def apply_key_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    for src, dest in _KEY_ALIASES.items():
        if src in out and dest not in out:
            out[dest] = out[src]
    return out


def deep_merge(*layers: dict[str, Any] | None) -> dict[str, Any]:
    """Merge dict layers left→right (later wins). Nested dicts merge recursively."""
    result: dict[str, Any] = {}
    for layer in layers:
        if not layer:
            continue
        for key, value in layer.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
    return result


def pick_allowed_keys(payload: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k in allowed}

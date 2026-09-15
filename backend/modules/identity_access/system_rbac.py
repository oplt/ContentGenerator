"""Compatibility facade — prefer system_roles for constants and helpers."""

from __future__ import annotations

from backend.modules.identity_access.system_roles import (
    DEFAULT_PERMISSIONS,
    SYSTEM_ROLES,
    _hash_token,
    hash_token,
)

__all__ = ["DEFAULT_PERMISSIONS", "SYSTEM_ROLES", "_hash_token", "hash_token"]

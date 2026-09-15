"""Cache policies for identity repository lookups."""

from __future__ import annotations

from backend.core.tenant_cache import OWNER_IDENTITY, CachePolicy

_TENANT_POLICY = CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=3600, negative_ttl_seconds=30)
_PERM_POLICY = CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=3600, negative_ttl_seconds=0)
_ROLE_POLICY = CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=3600, negative_ttl_seconds=30)

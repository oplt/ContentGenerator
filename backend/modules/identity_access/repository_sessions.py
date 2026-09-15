"""Refresh-session persistence and worker tenant listing."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.tenant_cache import (
    OWNER_IDENTITY,
    CachePolicy,
    build_cache_key,
    hydrate_orm,
    orm_column_dict,
    tenant_cache,
)
from backend.core.time_utils import utc_now_naive
from backend.modules.identity_access.models import RefreshSession, Tenant, TenantStatus


class SessionRepositoryMixin:
    """Refresh-token session CRUD — never cache auth material."""

    db: AsyncSession

    async def create_refresh_session(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> RefreshSession:
        session = RefreshSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(session)
        await self.db.flush()
        await tenant_cache.delete(
            f"active_sessions:{user_id}",
            f"refresh_session_by_hash:{token_hash}",
        )
        return session

    async def get_refresh_session_by_hash(self, token_hash: str) -> RefreshSession | None:
        # Never cache refresh sessions — auth material (T3.3).
        result = await self.db.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_session_by_id(self, session_id: uuid.UUID | str) -> RefreshSession | None:
        result = await self.db.execute(select(RefreshSession).where(RefreshSession.id == session_id))
        return result.scalar_one_or_none()

    async def revoke_refresh_session(self, session: RefreshSession) -> None:
        session.is_revoked = True
        await self.db.flush()
        await tenant_cache.delete(
            f"refresh_session_by_hash:{session.token_hash}",
            f"refresh_session_by_id:{session.id}",
            f"active_sessions:{session.user_id}",
        )

    async def list_active_sessions(self, user_id: uuid.UUID) -> list[RefreshSession]:
        result = await self.db.execute(
            select(RefreshSession).where(
                RefreshSession.user_id == user_id,
                RefreshSession.is_revoked.is_(False),
                RefreshSession.expires_at > utc_now_naive(),
            )
        )
        return list(result.scalars().all())


class TenantRepository:
    """Thin wrapper for tenant-level queries used by workers."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_active_tenants(self) -> list[Tenant]:
        """Return all non-suspended tenants for beat-scheduled fan-out tasks."""
        key = build_cache_key(
            owner=OWNER_IDENTITY,
            global_scope=True,
            identity="active_tenants",
        )

        async def _load() -> list[dict] | None:
            result = await self.db.execute(
                select(Tenant).where(
                    Tenant.status != TenantStatus.SUSPENDED.value,
                    Tenant.deleted_at.is_(None),
                )
            )
            tenants = list(result.scalars().all())
            return [orm_column_dict(t) for t in tenants]

        payload = await tenant_cache.get_or_set(
            key,
            policy=CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=600),
            factory=_load,
            legacy_keys=["active_tenants"],
        )
        if not payload:
            return []
        return [hydrate_orm(Tenant, item) for item in payload]

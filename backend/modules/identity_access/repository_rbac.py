"""Permission and role persistence with identity cache."""

from __future__ import annotations

import uuid

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
from backend.modules.identity_access.models import Permission, Role

_PERM_POLICY = CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=3600, negative_ttl_seconds=0)
_ROLE_POLICY = CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=3600, negative_ttl_seconds=30)


class RbacRepositoryMixin:
    """Global/tenant role and permission lookups."""

    db: AsyncSession

    async def list_permissions(self) -> list[Permission]:
        key = build_cache_key(
            owner=OWNER_IDENTITY,
            global_scope=True,
            identity="permissions:all",
        )

        async def _load() -> list[dict] | None:
            result = await self.db.execute(select(Permission).order_by(Permission.code.asc()))
            permissions = list(result.scalars().all())
            return [orm_column_dict(p) for p in permissions]

        payload = await tenant_cache.get_or_set(
            key,
            policy=_PERM_POLICY,
            factory=_load,
            legacy_keys=["all_permissions"],
        )
        if not payload:
            return []
        return [hydrate_orm(Permission, item) for item in payload]

    async def get_permission_by_code(self, code: str) -> Permission | None:
        key = build_cache_key(
            owner=OWNER_IDENTITY,
            global_scope=True,
            identity=f"permission:{code}",
        )

        async def _load() -> dict | None:
            result = await self.db.execute(select(Permission).where(Permission.code == code))
            permission = result.scalar_one_or_none()
            return orm_column_dict(permission) if permission else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_PERM_POLICY,
            factory=_load,
            legacy_keys=[f"permission_by_code:{code}"],
        )
        return hydrate_orm(Permission, payload) if payload else None

    async def create_permission(self, *, code: str, description: str, category: str) -> Permission:
        permission = Permission(code=code, description=description, category=category)
        self.db.add(permission)
        await self.db.flush()
        await tenant_cache.delete(
            build_cache_key(owner=OWNER_IDENTITY, global_scope=True, identity="permissions:all"),
            build_cache_key(owner=OWNER_IDENTITY, global_scope=True, identity=f"permission:{code}"),
            "all_permissions",
            f"permission_by_code:{code}",
        )
        return permission

    async def get_role(self, *, tenant_id: uuid.UUID | None, slug: str) -> Role | None:
        if tenant_id is None:
            key = build_cache_key(
                owner=OWNER_IDENTITY,
                global_scope=True,
                identity=f"role:{slug}",
            )
            legacy = [f"role:None:{slug}", f"role:{tenant_id}:{slug}"]
        else:
            key = build_cache_key(
                owner=OWNER_IDENTITY,
                tenant_id=tenant_id,
                identity=f"role:{slug}",
            )
            legacy = [f"role:{tenant_id}:{slug}"]

        async def _load() -> dict | None:
            result = await self.db.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.slug == slug)
            )
            role = result.scalar_one_or_none()
            return orm_column_dict(role) if role else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_ROLE_POLICY,
            factory=_load,
            legacy_keys=legacy,
        )
        return hydrate_orm(Role, payload) if payload else None

    async def create_role(
        self,
        *,
        tenant_id: uuid.UUID | None,
        name: str,
        slug: str,
        description: str,
        is_system: bool,
        permission_codes: list[str],
    ) -> Role:
        role = Role(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            description=description,
            is_system=is_system,
            permission_codes=permission_codes,
        )
        self.db.add(role)
        await self.db.flush()
        keys = [
            f"role:{tenant_id}:{slug}",
        ]
        if tenant_id is None:
            keys.append(
                build_cache_key(owner=OWNER_IDENTITY, global_scope=True, identity=f"role:{slug}")
            )
        else:
            keys.append(
                build_cache_key(
                    owner=OWNER_IDENTITY, tenant_id=tenant_id, identity=f"role:{slug}"
                )
            )
        if is_system:
            keys.extend(
                [
                    build_cache_key(
                        owner=OWNER_IDENTITY, global_scope=True, identity="permissions:all"
                    ),
                    "all_permissions",
                ]
            )
        await tenant_cache.delete(*keys)
        return role

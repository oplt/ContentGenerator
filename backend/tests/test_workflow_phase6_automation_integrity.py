"""Phase 6 — automation brand / version / account integrity."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import cast

import pytest
from fastapi import HTTPException
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.audit.models import AuditLog
from backend.modules.content_strategy.models import Brand, BrandSocialAccount
from backend.modules.identity_access.models import Tenant
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.automation_integrity import (
    authorize_brand_linked_accounts,
    require_active_brand,
    require_version_for_definition,
)
from backend.modules.workflows.automation_schemas import (
    AutomationCreateRequest,
    AutomationUpdateRequest,
)
from backend.modules.workflows.automation_service import AutomationService
from backend.modules.workflows.models import (
    Automation,
    AutomationTarget,
    WorkflowDefinition,
    WorkflowVersion,
)


async def _session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id CHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(
                    list[Table],
                    [
                        Tenant.__table__,
                        Brand.__table__,
                        SocialAccount.__table__,
                        BrandSocialAccount.__table__,
                        WorkflowDefinition.__table__,
                        WorkflowVersion.__table__,
                        Automation.__table__,
                        AutomationTarget.__table__,
                        AuditLog.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


async def _seed(
    db: AsyncSession,
    *,
    link_account: bool = True,
) -> tuple[Tenant, Brand, SocialAccount, WorkflowDefinition, WorkflowVersion]:
    tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    brand = Brand(tenant_id=tenant.id, name="Chess", niche="chess")
    db.add(brand)
    await db.flush()
    account = SocialAccount(
        tenant_id=tenant.id,
        platform="x",
        display_name="ChessX",
        handle="@chess",
        auth_type="stub",
        capability_flags={"text": "true"},
        settings={},
    )
    db.add(account)
    await db.flush()
    if link_account:
        db.add(
            BrandSocialAccount(
                tenant_id=tenant.id,
                brand_id=brand.id,
                social_account_id=account.id,
                enabled=True,
            )
        )
    definition = WorkflowDefinition(
        tenant_id=tenant.id, name="Daily", slug=f"daily-{uuid.uuid4().hex[:6]}", status="active"
    )
    db.add(definition)
    await db.flush()
    version = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json={"nodes": [], "edges": []},
        published_at=datetime.now(timezone.utc),
        checksum="c",
    )
    db.add(version)
    await db.flush()
    definition.current_version_id = version.id
    await db.commit()
    return tenant, brand, account, definition, version


def test_reject_unlinked_social_account() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, brand, account, definition, _version = await _seed(db, link_account=False)
        svc = AutomationService(db)
        with pytest.raises(HTTPException) as exc:
            await svc.create_automation(
                tenant.id,
                AutomationCreateRequest(
                    name="Morning",
                    workflow_definition_id=definition.id,
                    brand_id=brand.id,
                    social_account_ids=[account.id],
                ),
            )
        assert exc.value.status_code == 400
        detail = exc.value.detail
        assert isinstance(detail, dict)
        assert "unlinked_social_account_ids" in detail
        await db.close()

    asyncio.run(_run())


def test_allow_unlinked_override() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, brand, account, definition, _version = await _seed(db, link_account=False)
        svc = AutomationService(db)
        created = await svc.create_automation(
            tenant.id,
            AutomationCreateRequest(
                name="Override",
                workflow_definition_id=definition.id,
                brand_id=brand.id,
                social_account_ids=[account.id],
                allow_unlinked_targets=True,
            ),
        )
        assert len(created.targets) == 1
        await db.close()

    asyncio.run(_run())


def test_reject_version_from_other_definition() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, brand, account, definition, version = await _seed(db)
        other = WorkflowDefinition(
            tenant_id=tenant.id, name="Other", slug="other", status="active"
        )
        db.add(other)
        await db.flush()
        other_version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=other.id,
            version=1,
            graph_json={"nodes": [], "edges": []},
            published_at=datetime.now(timezone.utc),
            checksum="o",
        )
        db.add(other_version)
        await db.commit()

        with pytest.raises(HTTPException) as exc:
            await require_version_for_definition(
                db,
                tenant_id=tenant.id,
                workflow_definition_id=definition.id,
                workflow_version_id=other_version.id,
            )
        assert exc.value.status_code == 400
        assert "does not belong" in str(exc.value.detail)

        svc = AutomationService(db)
        with pytest.raises(HTTPException):
            await svc.create_automation(
                tenant.id,
                AutomationCreateRequest(
                    name="Bad",
                    workflow_definition_id=definition.id,
                    workflow_version_id=other_version.id,
                    brand_id=brand.id,
                    social_account_ids=[account.id],
                ),
            )
        await db.close()

    asyncio.run(_run())


def test_reject_deleted_brand() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, brand, account, definition, _version = await _seed(db)
        brand.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        with pytest.raises(HTTPException) as exc:
            await require_active_brand(db, tenant_id=tenant.id, brand_id=brand.id)
        assert exc.value.status_code == 400

        svc = AutomationService(db)
        with pytest.raises(HTTPException):
            await svc.create_automation(
                tenant.id,
                AutomationCreateRequest(
                    name="DeadBrand",
                    workflow_definition_id=definition.id,
                    brand_id=brand.id,
                    social_account_ids=[account.id],
                ),
            )
        await db.close()

    asyncio.run(_run())


def test_linked_account_create_succeeds() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, brand, account, definition, _version = await _seed(db)
        svc = AutomationService(db)
        created = await svc.create_automation(
            tenant.id,
            AutomationCreateRequest(
                name="Ok",
                workflow_definition_id=definition.id,
                brand_id=brand.id,
                social_account_ids=[account.id],
            ),
        )
        assert created.brand_id == brand.id
        assert created.targets[0].social_account_id == account.id
        await db.close()

    asyncio.run(_run())


def test_update_rejects_unlinked_when_brand_changes() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, brand, account, definition, _version = await _seed(db)
        other_brand = Brand(tenant_id=tenant.id, name="Tech", niche="tech")
        db.add(other_brand)
        await db.commit()

        svc = AutomationService(db)
        created = await svc.create_automation(
            tenant.id,
            AutomationCreateRequest(
                name="Move",
                workflow_definition_id=definition.id,
                brand_id=brand.id,
                social_account_ids=[account.id],
            ),
        )
        with pytest.raises(HTTPException) as exc:
            await svc.update_automation(
                tenant.id,
                created.id,
                AutomationUpdateRequest(brand_id=other_brand.id),
            )
        assert exc.value.status_code == 400
        await db.close()

    asyncio.run(_run())


def test_authorize_brand_linked_accounts_helper() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, brand, account, _d, _v = await _seed(db, link_account=True)
        await authorize_brand_linked_accounts(
            db,
            tenant_id=tenant.id,
            brand_id=brand.id,
            social_account_ids=[account.id],
        )
        await db.close()

    asyncio.run(_run())

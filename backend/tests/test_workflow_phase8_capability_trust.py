"""Phase 8 — do not trust client-supplied capability context."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, cast

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.capability_context import (
    build_runtime_compile_context,
    client_context_to_seed,
)
from backend.modules.workflows.compiler import WorkflowCompiler
from backend.modules.workflows.graph_schema import (
    CompileContext,
    DesignValidationContext,
    RuntimeClientContext,
)
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.runtime_bindings import authorize_runtime_bindings
from backend.modules.workflows.schemas import WorkflowStartRunRequest


@pytest.fixture(autouse=True)
def _registry() -> Any:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


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
                        WorkflowDefinition.__table__,
                        WorkflowVersion.__table__,
                        Automation.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


def _video_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {"id": "video", "type": "generate_video", "version": 1, "config": {}},
        ],
        "edges": [{"source": "trigger", "target": "video"}],
    }


def test_runtime_client_context_rejects_capability_maps() -> None:
    with pytest.raises(ValidationError):
        RuntimeClientContext.model_validate(
            {
                "social_account_ids": [str(uuid.uuid4())],
                "account_capabilities": {str(uuid.uuid4()): ["video"]},
            }
        )


def test_start_run_request_rejects_client_capability_maps() -> None:
    with pytest.raises(ValidationError):
        WorkflowStartRunRequest.model_validate(
            {
                "context": {
                    "social_account_ids": [str(uuid.uuid4())],
                    "account_capabilities": {"x": ["video"]},
                }
            }
        )


def test_client_context_to_seed_strips_maps() -> None:
    aid = uuid.uuid4()
    seeded = client_context_to_seed(
        CompileContext(
            social_account_ids=[aid],
            account_capabilities={str(aid): ["video", "llm"]},
            account_platforms={str(aid): "youtube"},
            require_publish_targets=False,
        )
    )
    assert seeded.social_account_ids == [aid]
    assert seeded.account_capabilities == {}
    assert seeded.account_platforms == {}
    assert seeded.require_publish_targets is False


def test_design_simulation_allows_hypothetical_video() -> None:
    account_id = uuid.uuid4()
    ctx = DesignValidationContext(
        social_account_ids=[account_id],
        account_capabilities={str(account_id): ["video", "llm", "publish"]},
        require_publish_targets=False,
    )
    result = WorkflowCompiler().validate_graph(_video_graph(), ctx)
    assert result.valid is True


def test_runtime_build_ignores_client_video_claim() -> None:
    async def _run() -> None:
        db = await _session()
        tenant = Tenant(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        account = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="X",
            handle="@x",
            auth_type="stub",
            status="connected",
            capability_flags={"text": "true", "video": "false"},
            settings={},
        )
        db.add(account)
        await db.flush()

        # Client lies: claims video via CompileContext maps.
        lying = CompileContext(
            social_account_ids=[account.id],
            account_capabilities={str(account.id): ["video", "llm", "publish"]},
            account_platforms={str(account.id): "youtube"},
            require_publish_targets=False,
            require_capability_check=True,
        )
        runtime = await build_runtime_compile_context(
            db, tenant_id=tenant.id, client=lying
        )
        tags = runtime.account_capabilities.get(str(account.id), [])
        assert "video" not in tags
        assert runtime.account_platforms[str(account.id)] == "x"
        assert runtime.account_statuses[str(account.id)] == "connected"

        result = WorkflowCompiler().validate_graph(_video_graph(), runtime)
        assert result.valid is False
        assert any(e.code == "incompatible_capabilities" for e in result.errors)
        await db.close()

    asyncio.run(_run())


def test_authorize_runtime_bindings_rejects_foreign_ids() -> None:
    async def _run() -> None:
        db = await _session()
        t1 = Tenant(name="a", slug=f"a-{uuid.uuid4().hex[:8]}")
        t2 = Tenant(name="b", slug=f"b-{uuid.uuid4().hex[:8]}")
        db.add_all([t1, t2])
        await db.flush()
        brand = Brand(tenant_id=t1.id, name="b", niche="n")
        db.add(brand)
        await db.flush()
        account = SocialAccount(
            tenant_id=t1.id,
            platform="x",
            display_name="X",
            handle="@x",
            auth_type="stub",
            status="connected",
            capability_flags={"text": "true"},
            settings={},
        )
        db.add(account)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=t1.id, name="wf", slug=f"wf-{uuid.uuid4().hex[:8]}", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=t1.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json={"nodes": [], "edges": []},
            published_at=datetime.now(timezone.utc),
            checksum="c",
        )
        db.add(version)
        await db.flush()
        automation = Automation(
            tenant_id=t1.id,
            workflow_definition_id=definition.id,
            workflow_version_id=version.id,
            brand_id=brand.id,
            name="auto",
            enabled=True,
            trigger_type="manual",
            trigger_config={},
            timezone="UTC",
        )
        db.add(automation)
        await db.flush()

        with pytest.raises(HTTPException) as foreign_account:
            await authorize_runtime_bindings(
                db,
                tenant_id=t2.id,
                social_account_ids=[account.id],
            )
        assert foreign_account.value.status_code == 403

        with pytest.raises(HTTPException) as foreign_auto:
            await authorize_runtime_bindings(
                db,
                tenant_id=t2.id,
                automation_id=automation.id,
            )
        assert foreign_auto.value.status_code == 400

        with pytest.raises(HTTPException) as foreign_brand:
            await authorize_runtime_bindings(
                db,
                tenant_id=t2.id,
                brand_id=brand.id,
            )
        assert foreign_brand.value.status_code == 400

        # Happy path
        await authorize_runtime_bindings(
            db,
            tenant_id=t1.id,
            automation_id=automation.id,
            brand_id=brand.id,
            social_account_ids=[account.id],
        )
        await db.close()

    asyncio.run(_run())


def test_disconnected_account_rejected_at_runtime() -> None:
    async def _run() -> None:
        db = await _session()
        tenant = Tenant(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        account = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="X",
            handle="@x",
            auth_type="stub",
            status="disconnected",
            capability_flags={"text": "true", "video": "true"},
            settings={},
        )
        db.add(account)
        await db.flush()
        with pytest.raises(HTTPException) as exc:
            await build_runtime_compile_context(
                db,
                tenant_id=tenant.id,
                client=RuntimeClientContext(social_account_ids=[account.id]),
            )
        assert exc.value.status_code == 400
        await db.close()

    asyncio.run(_run())

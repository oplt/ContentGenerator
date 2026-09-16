"""Phase 8 — configuration precedence resolver."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, cast

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_strategy.models import Brand, BrandProfile, BrandSocialAccount
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.config_merge import deep_merge, strip_secrets
from backend.modules.workflows.config_resolver import ConfigResolver, PRECEDENCE
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph
from backend.modules.workflows.models import (
    Automation,
    AutomationTarget,
    AutomationTriggerType,
    WorkflowDefinition,
    WorkflowVersion,
)
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowRun


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"temperature": 0.4, "max_tokens": 100},
            },
        ],
        "edges": [{"source": "trigger", "target": "generate"}],
    }


def test_deep_merge_and_strip_secrets() -> None:
    merged = deep_merge({"a": 1, "nested": {"x": 1}}, {"a": 2, "nested": {"y": 2}})
    assert merged == {"a": 2, "nested": {"x": 1, "y": 2}}
    cleaned = strip_secrets({"tone": "warm", "api_key": "secret", "oauth_token": "x"})
    assert cleaned == {"tone": "warm"}
    assert "api_key" not in cleaned


def test_resolve_node_config_precedence() -> None:
    resolver = ConfigResolver.__new__(ConfigResolver)
    resolver.registry = build_default_registry()
    resolved = resolver.resolve_node_config(
        node_type="generate_text",
        node_version=1,
        graph_config={"temperature": 0.4, "max_tokens": 100},
        brand_layer={"tone": "educational", "temperature": 0.5},
        automation_layer={"tone": "enthusiastic"},
        automation_node_overrides={},
        account_layer={"max_length": 250},  # alias → max_tokens
        account_node_overrides={},
        run_layer={"temperature": 0.9},
    )
    assert resolved["tone"] == "enthusiastic"
    assert resolved["temperature"] == 0.9
    assert resolved["max_tokens"] == 250


async def _async_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
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
                        BrandProfile.__table__,
                        SocialAccount.__table__,
                        BrandSocialAccount.__table__,
                        WorkflowDefinition.__table__,
                        WorkflowVersion.__table__,
                        Automation.__table__,
                        AutomationTarget.__table__,
                        TaskExecution.__table__,
                        WorkflowRun.__table__,
                        WorkflowNodeRun.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_build_snapshot_freezes_resolved_config() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        brand = Brand(
            tenant_id=tenant.id,
            name="Chess",
            niche="chess",
            style_guide={"tone": "professional"},
        )
        db.add(brand)
        await db.flush()
        profile = BrandProfile(
            tenant_id=tenant.id,
            brand_id=brand.id,
            name="Chess Voice",
            tone="educational",
            audience="players",
        )
        account = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="Chess X",
            handle="@chess",
            account_external_id="x-1",
            capability_flags={"llm": "1"},
            settings={"oauth_token": "should-not-leak"},
        )
        db.add_all([profile, account])
        await db.flush()
        db.add(
            BrandSocialAccount(
                tenant_id=tenant.id,
                brand_id=brand.id,
                social_account_id=account.id,
                generation_overrides={"max_length": 220, "api_key": "nope"},
            )
        )
        definition = WorkflowDefinition(
            tenant_id=tenant.id,
            name="Cfg",
            slug=f"cfg-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=_graph(),
            published_at=datetime.now(timezone.utc),
            checksum="cfg",
        )
        db.add(version)
        await db.flush()
        definition.current_version_id = version.id
        automation = Automation(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            workflow_version_id=version.id,
            brand_id=brand.id,
            name="Daily",
            enabled=True,
            trigger_type=AutomationTriggerType.MANUAL.value,
            settings={
                "editorial": {"tone": "enthusiastic"},
                "node_overrides": {"generate": {"temperature": 0.55}},
            },
        )
        db.add(automation)
        await db.flush()
        db.add(
            AutomationTarget(
                tenant_id=tenant.id,
                automation_id=automation.id,
                social_account_id=account.id,
                overrides_json={},
            )
        )
        await db.flush()

        engine = WorkflowEngine(db)
        run = await engine.start_run(
            tenant_id=tenant.id,
            workflow_version_id=version.id,
            automation_id=automation.id,
            brand_id=brand.id,
            trigger_payload={"prompt": "hello", "config": {"temperature": 0.8}},
            compile_context=CompileContext(social_account_ids=[account.id]),
            advance=False,
            correlation_id=f"cfg-{uuid.uuid4().hex[:8]}",
        )
        snap = dict(run.context_snapshot or {})
        assert snap["config_precedence"] == list(PRECEDENCE)
        assert snap["brand_profile"]["tone"] == "educational"
        assert snap["resolved_editorial"]["tone"] == "educational"
        gen = snap["resolved_node_configs"]["generate"]
        assert gen["tone"] == "enthusiastic"
        assert gen["temperature"] == 0.8
        assert gen["max_tokens"] == 220
        assert "api_key" not in gen
        assert "oauth_token" not in str(snap["accounts"])
        assert snap["providers"]["llm"]
        # Historical freeze: mutating brand after start must not change snapshot.
        profile.tone = "changed-later"
        await db.flush()
        assert snap["resolved_node_configs"]["generate"]["tone"] == "enthusiastic"
        await db.close()

    asyncio.run(_run())


def test_resolver_unit_graph_validate() -> None:
    graph = WorkflowGraph.model_validate(_graph())
    assert len(graph.nodes) == 2

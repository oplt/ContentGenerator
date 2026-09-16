"""Phase 10 — PlatformTransform persists ContentVariant; Publish consumes it."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_generation.models import ContentVariant, ContentVariantTarget
from backend.modules.content_generation.variant_store import (
    ContentVariantStore,
    VariantSnapshot,
    assets_from_variant_snapshot,
    snapshot_from_provider_payload,
)
from backend.modules.identity_access.models import Tenant
from backend.modules.publishing.account_selection import build_publish_idempotency_key
from backend.modules.publishing.models import SocialAccount
from backend.modules.publishing.schemas import PublishNowRequest
from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.nodes.platform_transform import (
    PlatformTransformConfig,
    PlatformTransformInput,
    PlatformTransformNode,
)
from backend.modules.workflows.registry import build_default_registry, reset_default_registry


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
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(
                    list[Table],
                    [
                        Tenant.__table__,
                        SocialAccount.__table__,
                        ContentVariant.__table__,
                        ContentVariantTarget.__table__,
                    ],
                ),
            )
        )
        # Stub content_jobs for composite FK (full content-plan chain not needed).
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS content_jobs (
                    id CHAR(32) NOT NULL PRIMARY KEY,
                    tenant_id CHAR(32) NOT NULL,
                    UNIQUE (tenant_id, id)
                )
                """
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


async def _seed_job(db: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    job_id = uuid.uuid4()
    # Match SQLAlchemy Uuid storage on SQLite (32-char hex, no dashes).
    await db.execute(
        text("INSERT INTO content_jobs (id, tenant_id) VALUES (:id, :tid)"),
        {"id": job_id.hex, "tid": tenant_id.hex},
    )
    return job_id


def test_variant_snapshot_provider_payload_roundtrip() -> None:
    vid = uuid.uuid4()
    snap = VariantSnapshot(
        variant_id=vid,
        content_job_id=uuid.uuid4(),
        fingerprint="x:abc",
        platform="x",
        text="Adapted post body",
        title=None,
        description=None,
        tags=("chess",),
        social_account_ids=(uuid.uuid4(),),
    )
    payload = snap.as_provider_payload()
    assert payload["variant_source"] == "content_variant"
    assert payload["variant_text"] == "Adapted post body"
    rebuilt = snapshot_from_provider_payload(payload)
    assert rebuilt is not None
    assert rebuilt.variant_id == vid
    assert rebuilt.text == "Adapted post body"


def test_assets_from_variant_prefer_variant_text_over_generated() -> None:
    snap = VariantSnapshot(
        variant_id=uuid.uuid4(),
        content_job_id=uuid.uuid4(),
        fingerprint="x:abc",
        platform="x",
        text="VARIANT TEXT",
    )

    class _Asset:
        def __init__(self, asset_type: str, text: str) -> None:
            self.asset_type = asset_type
            self.text_content = text
            self.platform = "x"

    assets = assets_from_variant_snapshot(
        snap,
        media_assets=[
            _Asset("text_variant", "OLD GENERATED"),
            _Asset("video", ""),
        ],
    )
    assert assets[0].text_content == "VARIANT TEXT"
    assert assets[0].asset_type == "text_variant"
    assert len(assets) == 2
    assert assets[1].asset_type == "video"


def test_idempotency_includes_variant_identity() -> None:
    job_id = uuid.uuid4()
    account_id = uuid.uuid4()
    variant_id = uuid.uuid4()
    without = build_publish_idempotency_key(
        content_job_id=job_id,
        social_account_id=account_id,
        scheduled_for=None,
        dry_run=True,
    )
    with_variant = build_publish_idempotency_key(
        content_job_id=job_id,
        social_account_id=account_id,
        scheduled_for=None,
        dry_run=True,
        content_variant_id=variant_id,
    )
    assert without != with_variant
    assert str(variant_id) in with_variant
    assert without == f"{job_id}:{account_id}:immediate:publish:dry"


def test_publish_now_request_has_no_raw_provider_payload_field() -> None:
    assert "provider_payload" not in PublishNowRequest.model_fields
    assert "content_variant_ids" in PublishNowRequest.model_fields


def test_content_variant_store_upsert_and_resolve() -> None:
    async def _run() -> None:
        db = await _session()
        tenant = Tenant(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        job_id = await _seed_job(db, tenant.id)
        account = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="X Main",
            handle="@x",
            account_external_id=f"ext-{uuid.uuid4().hex[:8]}",
            status="connected",
            capability_flags={"text": "true"},
            account_metadata={"mode": "stub"},
            settings={},
        )
        db.add(account)
        await db.flush()

        store = ContentVariantStore(db)
        saved = await store.upsert_variant(
            tenant_id=tenant.id,
            content_job_id=job_id,
            fingerprint="x:fp1",
            platform="x",
            text="Adapted once",
            social_account_ids=[account.id],
            tags=["chess"],
        )
        again = await store.upsert_variant(
            tenant_id=tenant.id,
            content_job_id=job_id,
            fingerprint="x:fp1",
            platform="x",
            text="Adapted once (updated)",
            social_account_ids=[account.id],
        )
        assert again.id == saved.id
        assert again.text == "Adapted once (updated)"

        snap = await store.resolve_for_account(
            tenant_id=tenant.id,
            content_job_id=job_id,
            social_account_id=account.id,
        )
        assert snap is not None
        assert snap.variant_id == saved.id
        assert snap.text == "Adapted once (updated)"
        assert account.id in snap.social_account_ids
        await db.close()

    asyncio.run(_run())


def test_platform_transform_persists_variants_when_job_present() -> None:
    async def _run() -> None:
        db = await _session()
        tenant = Tenant(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        job_id = await _seed_job(db, tenant.id)
        account = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="X Main",
            handle="@x",
            account_external_id=f"ext-{uuid.uuid4().hex[:8]}",
            status="connected",
            capability_flags={"text": "true"},
            account_metadata={"mode": "stub"},
            settings={},
        )
        db.add(account)
        await db.flush()

        ctx = build_node_context(
            tenant_id=tenant.id,
            db=db,
            workflow_run_id=uuid.uuid4(),
        )
        node = PlatformTransformNode()
        result = await node.execute(
            ctx,
            PlatformTransformInput(
                text="Canonical editorial body about a historic chess game.",
                hashtags=["chess"],
                social_account_ids=[account.id],
                content_job_id=job_id,
            ),
            PlatformTransformConfig(),
        )
        assert result.status.value == "succeeded"
        assert result.output["variant_ids"]
        variant_id = uuid.UUID(str(result.output["variant_ids"][0]))
        store = ContentVariantStore(db)
        snap = await store.get_snapshot(tenant.id, variant_id)
        assert snap is not None
        assert snap.text
        assert account.id in snap.social_account_ids
        assert result.output["variants"][0]["id"] == str(variant_id)
        await db.close()

    asyncio.run(_run())


def test_publish_orchestration_snapshots_variant_into_job() -> None:
    async def _run() -> None:
        from backend.modules.publishing import publish_orchestration as orch

        tenant_id = uuid.uuid4()
        job_id = uuid.uuid4()
        account_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        snap = VariantSnapshot(
            variant_id=variant_id,
            content_job_id=job_id,
            fingerprint="x:fp",
            platform="x",
            text="FROM VARIANT",
            social_account_ids=(account_id,),
        )

        account = MagicMock()
        account.id = account_id
        account.platform = "x"
        account.account_external_id = "ext"
        account.account_metadata = {"mode": "stub"}

        content_job = MagicMock()
        content_job.id = job_id
        content_job.target_social_account_ids = [str(account_id)]

        created_jobs: list[Any] = []

        async def _create(job: Any) -> Any:
            created_jobs.append(job)
            job.id = uuid.uuid4()
            return job

        svc = MagicMock()
        svc.db = MagicMock()
        svc.db.flush = AsyncMock()
        svc.content_repo.get_job = AsyncMock(return_value=content_job)
        svc.content_repo.list_assets = AsyncMock(return_value=[])
        svc.repo.get_job_by_idempotency = AsyncMock(return_value=None)
        svc.repo.get_connected_for_social = AsyncMock(return_value=None)
        svc.repo.get_connected_account_by_platform = AsyncMock(return_value=None)
        svc.repo.create_publishing_job = AsyncMock(side_effect=_create)
        svc._publish_job = AsyncMock(side_effect=lambda *a, **k: created_jobs[-1])

        with (
            patch(
                "backend.modules.publishing.publish_orchestration.resolve_social_accounts",
                new=AsyncMock(return_value=[account]),
            ),
            patch(
                "backend.modules.publishing.publish_orchestration.ContentVariantStore"
            ) as store_cls,
            patch(
                "backend.modules.publishing.publish_orchestration.get_provider",
            ) as get_provider,
            patch(
                "backend.modules.identity_access.repository.IdentityAccessRepository.get_tenant_by_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            store = store_cls.return_value
            store.resolve_for_account = AsyncMock(return_value=snap)
            provider = MagicMock()
            provider.schedule_publish = AsyncMock()
            get_provider.return_value = provider

            jobs = await orch.publish_now(
                svc,
                tenant_id=tenant_id,
                approval_request_id=None,
                payload=PublishNowRequest(
                    content_job_id=job_id,
                    social_account_ids=[account_id],
                    content_variant_ids=[variant_id],
                    dry_run=True,
                ),
            )

        assert len(jobs) == 1
        job = created_jobs[0]
        assert job.content_variant_id == variant_id
        assert job.provider_payload["variant_text"] == "FROM VARIANT"
        assert job.provider_payload["variant_source"] == "content_variant"
        assert str(variant_id) in job.idempotency_key

    asyncio.run(_run())


def test_legacy_publish_inputs_forward_variant_ids() -> None:
    from backend.modules.workflows.engine_inputs_legacy import resolve_legacy_node_inputs

    vid = str(uuid.uuid4())
    inputs = resolve_legacy_node_inputs(
        node_type="publish",
        trigger_payload={},
        initial_inputs={
            "content_job_id": str(uuid.uuid4()),
            "variant_ids": [vid],
            "social_account_ids": [str(uuid.uuid4())],
        },
        upstream_outputs=[],
        run_id=uuid.uuid4(),
    )
    assert inputs["content_variant_ids"] == [vid]

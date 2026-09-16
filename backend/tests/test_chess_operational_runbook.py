"""§33 — operational runbook maps ops onto existing CLI/jobs/APIs."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast

from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.catalog_job_router import router as job_router
from backend.modules.chess_intelligence.operational_runbook import (
    RUNBOOK_OPS,
    runbook_operations,
)
from backend.modules.chess_intelligence.provider_sync_state import (
    ChessProviderSyncState,
    ChessProviderSyncStateService,
)
from backend.modules.identity_access.models import Tenant


def test_runbook_covers_prompt_operations() -> None:
    ops = set(runbook_operations())
    assert ops == {
        "bootstrap_historical_archive",
        "run_historical_famous_enrichment",
        "run_recent_provider_sync",
        "refresh_daily_puzzle",
        "inspect_synchronization_state",
        "retry_failed_synchronization",
        "reanalyze_changed_engine_profile",
    }
    assert all(op.primary for op in RUNBOOK_OPS)


def test_sync_states_route_registered() -> None:
    paths = {getattr(r, "path", None) for r in job_router.routes}
    assert "/sync-states" in paths


def test_list_for_tenant_returns_checkpoints() -> None:
    async def _run() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine.sync_engine, "connect")
        def _fk_off(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.close()

        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn,
                    tables=cast(
                        list[Table],
                        [Tenant.__table__, ChessProviderSyncState.__table__],
                    ),
                )
            )
        db = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        svc = ChessProviderSyncStateService(db)
        await svc.get_or_create(
            tenant_id=tenant_id, provider="lichess_masters", params={}
        )
        await svc.get_or_create(
            tenant_id=tenant_id, provider="chesscom", params={"player": "hikaru"}
        )
        rows = await svc.list_for_tenant(tenant_id=tenant_id)
        assert len(rows) == 2
        assert {r.provider for r in rows} == {"lichess_masters", "chesscom"}

    asyncio.run(_run())

"""§11 / §26 — chess catalog scheduling via Celery beat + ChessCatalogJob only."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import cast
from unittest.mock import patch

from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.catalog_job_models import (
    ChessCatalogJob,
    ChessCatalogJobKind,
)
from backend.modules.chess_intelligence.catalog_job_service import ChessCatalogJobService
from backend.modules.chess_intelligence.catalog_schedule import (
    CATALOG_OPERATION_CADENCE,
    FORBIDDEN_AUTO_SCHEDULE_TOKENS,
    MANUAL_ONLY_JOB_KINDS,
    SCHEDULED_JOB_KINDS,
    build_chess_catalog_beat_schedule,
    forbidden_auto_schedule_hits,
    provider_sync_schedule,
)
from backend.modules.identity_access.models import Tenant
from backend.workers.celery_app import celery_app
from backend.workers.task_policy import TASK_POLICIES


def test_scheduled_kinds_are_subset_of_catalog_jobs() -> None:
    allowed = {k.value for k in ChessCatalogJobKind}
    assert SCHEDULED_JOB_KINDS <= allowed
    assert MANUAL_ONLY_JOB_KINDS <= allowed
    assert SCHEDULED_JOB_KINDS.isdisjoint(MANUAL_ONLY_JOB_KINDS)


def test_operation_cadence_covers_section_26_ops() -> None:
    kinds = {row.kind for row in CATALOG_OPERATION_CADENCE if row.kind}
    assert ChessCatalogJobKind.PGN_IMPORT.value in kinds
    assert ChessCatalogJobKind.PROVIDER_SYNC.value in kinds
    assert ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value in kinds
    assert ChessCatalogJobKind.ENRICH_FAMOUS.value in kinds
    by_kind = {r.kind: r for r in CATALOG_OPERATION_CADENCE}
    assert by_kind[ChessCatalogJobKind.PROVIDER_SYNC.value].cadence == "configurable"
    assert by_kind[ChessCatalogJobKind.ENRICH_FAMOUS.value].cadence == "manual"
    stockfish = [r for r in CATALOG_OPERATION_CADENCE if r.kind is None]
    assert stockfish and stockfish[0].cadence == "on_demand"


def test_build_beat_respects_enable_flags() -> None:
    empty = build_chess_catalog_beat_schedule(
        daily_puzzle_enabled=False,
        daily_puzzle_hour=0,
        daily_puzzle_minute=20,
        provider_sync_enabled=False,
        provider_sync_hour=6,
        provider_sync_minute=30,
    )
    assert empty == {}

    both = build_chess_catalog_beat_schedule(
        daily_puzzle_enabled=True,
        daily_puzzle_hour=1,
        daily_puzzle_minute=5,
        provider_sync_enabled=True,
        provider_sync_hour=7,
        provider_sync_minute=15,
    )
    assert set(both) == {"chess-daily-puzzle-sync", "chess-provider-sync-recent"}
    assert both["chess-daily-puzzle-sync"]["task"].endswith(
        "chess_catalog_daily_puzzle_fanout_task"
    )
    assert both["chess-provider-sync-recent"]["task"].endswith(
        "chess_catalog_provider_sync_fanout_task"
    )


def test_provider_sync_optional_interval_for_tournament_feeds() -> None:
    daily = provider_sync_schedule(hour=6, minute=30, every_minutes=None)
    assert getattr(daily, "hour", None) == {6} or "6" in str(daily)
    interval = provider_sync_schedule(hour=6, minute=30, every_minutes=60)
    assert interval == timedelta(minutes=60)

    beat = build_chess_catalog_beat_schedule(
        daily_puzzle_enabled=False,
        daily_puzzle_hour=0,
        daily_puzzle_minute=0,
        provider_sync_enabled=True,
        provider_sync_hour=6,
        provider_sync_minute=30,
        provider_sync_every_minutes=45,
    )
    assert beat["chess-provider-sync-recent"]["schedule"] == timedelta(minutes=45)


def test_forbidden_tokens_block_historical_redownload_and_bulk_reanalyze() -> None:
    assert "pgn_import" in FORBIDDEN_AUTO_SCHEDULE_TOKENS
    assert "reanalyze_all" in FORBIDDEN_AUTO_SCHEDULE_TOKENS
    assert "daily_reanalysis" in FORBIDDEN_AUTO_SCHEDULE_TOKENS
    bad = {
        "chess-reanalyze-all-daily": {
            "task": "backend.workers.tasks.reanalyze_all_games_task",
            "schedule": timedelta(days=1),
        },
        "ok-daily-puzzle": {
            "task": "backend.workers.tasks.chess_catalog_daily_puzzle_fanout_task",
            "schedule": timedelta(days=1),
        },
    }
    assert forbidden_auto_schedule_hits(bad) == ["chess-reanalyze-all-daily"]


def test_live_beat_has_daily_puzzle_not_forbidden_schedules() -> None:
    beat = dict(celery_app.conf.beat_schedule or {})
    assert "chess-daily-puzzle-sync" in beat
    assert "chess-provider-sync-recent" not in beat  # disabled by default
    assert forbidden_auto_schedule_hits(beat) == []
    blob = " ".join(str(beat[k]) for k in beat if k.startswith("chess-"))
    for token in MANUAL_ONLY_JOB_KINDS:
        assert token not in blob


def test_fanout_task_policies_registered() -> None:
    assert "backend.workers.tasks.chess_catalog_daily_puzzle_fanout_task" in TASK_POLICIES
    assert "backend.workers.tasks.chess_catalog_provider_sync_fanout_task" in TASK_POLICIES


async def _session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(
                    list[Table],
                    [Tenant.__table__, ChessCatalogJob.__table__],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_enqueue_daily_puzzle_sync_needs_no_file_path() -> None:
    async def _run() -> None:
        from backend.modules.chess_intelligence.ingestion_mode import (
            METADATA_KEY,
            ChessIngestionMode,
        )

        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        job = await ChessCatalogJobService(db).enqueue(
            tenant_id=tenant_id,
            user_id=None,
            kind=ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value,
            params={"via": "test"},
        )
        assert job.kind == ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value
        assert job.params[METADATA_KEY] == ChessIngestionMode.PUZZLE_SYNC.value

    asyncio.run(_run())


def test_daily_puzzle_fanout_dispatches_run_catalog_job() -> None:
    from backend.workers.task_defs.chess_catalog import chess_catalog_daily_puzzle_fanout_task

    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()
    with (
        patch(
            "backend.workers.task_defs.chess_catalog.run_async_task_simple",
            return_value={
                "kind": ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value,
                "tenants_dispatched": 1,
                "jobs": [(str(tenant_id), str(job_id))],
            },
        ),
        patch(
            "backend.workers.task_defs.chess_catalog.run_chess_catalog_job_task"
        ) as run_task,
    ):
        result = chess_catalog_daily_puzzle_fanout_task()
    assert result["tenants_dispatched"] == 1
    assert result["kind"] == ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value
    run_task.delay.assert_called_once_with(
        tenant_id=str(tenant_id), job_id=str(job_id)
    )

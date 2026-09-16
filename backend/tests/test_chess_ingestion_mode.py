"""Hybrid ingestion lifecycle modes (Phase hybrid §2)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.catalog_job_models import (
    ChessCatalogJob,
    ChessCatalogJobKind,
)
from backend.modules.chess_intelligence.catalog_job_service import ChessCatalogJobService
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.ingestion_mode import (
    METADATA_KEY,
    MODE_PROFILES,
    ChessIngestionMode,
    ensure_job_params_mode,
    mode_for_catalog_job_kind,
    profile_for,
    stamp_ingestion_mode,
)
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource, ChessPuzzle
from backend.modules.chess_intelligence.normalizer import (
    chess_game_from_parsed,
    chess_puzzle_from_fields,
)
from backend.modules.chess_intelligence.repository import ChessPuzzleRepository
from backend.modules.chess_intelligence.schemas import ChessGameImportRequest
from backend.modules.chess_intelligence.service import ChessCatalogService
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

_PGN = """
[Event "Test"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
"""


def test_all_four_modes_have_profiles() -> None:
    assert set(MODE_PROFILES) == set(ChessIngestionMode)
    assert profile_for(ChessIngestionMode.HISTORICAL_BOOTSTRAP).bulk_oriented
    assert profile_for(ChessIngestionMode.RECENT_DISCOVERY).incremental
    assert profile_for(ChessIngestionMode.RECENT_DISCOVERY).checkpointed
    assert profile_for(ChessIngestionMode.PUZZLE_SYNC).reads_local_catalog
    assert not profile_for(ChessIngestionMode.HISTORICAL_BOOTSTRAP).requires_live_http_after_import


def test_job_kind_maps_to_ingestion_mode() -> None:
    assert (
        mode_for_catalog_job_kind(ChessCatalogJobKind.PGN_IMPORT.value)
        == ChessIngestionMode.HISTORICAL_BOOTSTRAP
    )
    assert (
        mode_for_catalog_job_kind(ChessCatalogJobKind.PROVIDER_SYNC.value)
        == ChessIngestionMode.RECENT_DISCOVERY
    )
    assert (
        mode_for_catalog_job_kind(ChessCatalogJobKind.PUZZLE_IMPORT.value)
        == ChessIngestionMode.PUZZLE_SYNC
    )
    assert (
        mode_for_catalog_job_kind(ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value)
        == ChessIngestionMode.PUZZLE_SYNC
    )
    assert mode_for_catalog_job_kind(ChessCatalogJobKind.ENRICH_FAMOUS.value) is None
    assert mode_for_catalog_job_kind(ChessCatalogJobKind.EXTRACT_CRITICAL_MOMENTS.value) is None


def test_ensure_job_params_stamps_mode() -> None:
    stamped = ensure_job_params_mode(
        ChessCatalogJobKind.PROVIDER_SYNC.value,
        {"provider": "lichess_masters"},
    )
    assert stamped["provider"] == "lichess_masters"
    assert stamped[METADATA_KEY] == ChessIngestionMode.RECENT_DISCOVERY.value
    untouched = ensure_job_params_mode(
        ChessCatalogJobKind.ENRICH_FAMOUS.value,
        {"dry_run": True},
    )
    assert METADATA_KEY not in untouched


async def _catalog_session(*, include_jobs: bool = False) -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        # Jobs FK → users; keep off when User table omitted (same as catalog job tests).
        cursor.execute("PRAGMA foreign_keys=OFF" if include_jobs else "PRAGMA foreign_keys=ON")
        cursor.close()

    tables: list[Table] = [
        Tenant.__table__,
        ChessGame.__table__,
        ChessGameSource.__table__,
        ChessPuzzle.__table__,
    ]
    if include_jobs:
        tables.append(ChessCatalogJob.__table__)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables)
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_enqueue_stamps_ingestion_mode_on_params() -> None:
    async def _run() -> None:
        db = await _catalog_session(include_jobs=True)
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        job = await ChessCatalogJobService(db).enqueue(
            tenant_id=tenant_id,
            user_id=None,
            kind=ChessCatalogJobKind.PGN_IMPORT.value,
            params={"file_path": "/tmp/x.pgn"},
        )
        assert job.params[METADATA_KEY] == ChessIngestionMode.HISTORICAL_BOOTSTRAP.value

    asyncio.run(_run())


def test_manual_import_stamps_mode_and_uses_dedupe() -> None:
    async def _run() -> None:
        db = await _catalog_session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        svc = ChessCatalogService(db)
        first = await svc.import_game(
            tenant_id=tenant_id,
            payload=ChessGameImportRequest(pgn=_PGN, provider="manual"),
        )
        assert first.created_game is True
        sources = (
            await db.execute(
                select(ChessGameSource).where(ChessGameSource.chess_game_id == first.game.id)
            )
        ).scalars().all()
        assert len(sources) == 1
        assert sources[0].source_metadata[METADATA_KEY] == ChessIngestionMode.MANUAL_IMPORT.value

        second = await svc.import_game(
            tenant_id=tenant_id,
            payload=ChessGameImportRequest(
                pgn=_PGN,
                provider="api_import",
                external_id="ext-1",
            ),
        )
        assert second.created_game is False
        assert second.created_source is True
        assert second.game.id == first.game.id

    asyncio.run(_run())


def test_recent_discovery_source_stamp_via_dedupe() -> None:
    async def _run() -> None:
        db = await _catalog_session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        parsed = parse_chess_input(_PGN, "pgn")
        game = chess_game_from_parsed(
            tenant_id=tenant_id,
            parsed=parsed,
            source_provider="lichess_masters",
        )
        outcome = await ChessGameDedupeService(db).upsert_game(
            game=game,
            source=SourceRef(
                provider="lichess_masters",
                external_id="abc",
                source_metadata=stamp_ingestion_mode(
                    {}, ChessIngestionMode.RECENT_DISCOVERY
                ),
            ),
        )
        assert outcome.created_game is True
        src = (
            await db.execute(
                select(ChessGameSource).where(ChessGameSource.chess_game_id == outcome.game.id)
            )
        ).scalar_one()
        assert src.source_metadata[METADATA_KEY] == ChessIngestionMode.RECENT_DISCOVERY.value

    asyncio.run(_run())


def test_daily_puzzle_prefers_local_catalog() -> None:
    async def _run() -> None:
        db = await _catalog_session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        puzzle = chess_puzzle_from_fields(
            tenant_id=tenant_id,
            external_id="daily-local",
            provider="lichess_puzzles",
            starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            solution_moves_uci=["e2e4"],
            solution_moves_san=["e4"],
            source_metadata=stamp_ingestion_mode(
                {"daily_utc": day, "via": "daily_puzzle_sync"},
                ChessIngestionMode.PUZZLE_SYNC,
            ),
            retrieved_at=datetime.now(timezone.utc),
        )
        await ChessPuzzleRepository(db).add(puzzle)
        await db.flush()

        with patch(
            "backend.modules.chess_intelligence.service.get_puzzle_provider"
        ) as provider_cls:
            provider_cls.return_value.get_daily_puzzle = AsyncMock(
                side_effect=AssertionError("must not call provider when local daily exists")
            )
            resp = await ChessCatalogService(db).get_daily_puzzle(tenant_id=tenant_id)
        assert resp.external_id == "daily-local"
        assert resp.id == puzzle.id
        assert resp.is_stale is False
        assert resp.freshness == "fresh"
        assert resp.daily_utc == day
        provider_cls.assert_not_called()

    asyncio.run(_run())


def test_daily_puzzle_get_miss_is_404_without_provider() -> None:
    async def _run() -> None:
        from fastapi import HTTPException

        db = await _catalog_session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()

        with patch(
            "backend.modules.chess_intelligence.service.get_puzzle_provider"
        ) as provider_cls:
            provider_cls.return_value.get_daily_puzzle = AsyncMock(
                side_effect=AssertionError("GET must not call provider on miss")
            )
            try:
                await ChessCatalogService(db).get_daily_puzzle(tenant_id=tenant_id)
                raise AssertionError("expected 404")
            except HTTPException as exc:
                assert exc.status_code == 404
                assert "local catalog" in str(exc.detail).lower()
        provider_cls.assert_not_called()

    asyncio.run(_run())


def test_daily_puzzle_get_returns_stale_without_provider() -> None:
    async def _run() -> None:
        db = await _catalog_session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        puzzle = chess_puzzle_from_fields(
            tenant_id=tenant_id,
            external_id="daily-stale",
            provider="lichess_puzzles",
            starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            solution_moves_uci=["e2e4"],
            solution_moves_san=["e4"],
            source_metadata=stamp_ingestion_mode(
                {"daily_utc": "2020-01-01", "via": "daily_puzzle_sync"},
                ChessIngestionMode.PUZZLE_SYNC,
            ),
            retrieved_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        await ChessPuzzleRepository(db).add(puzzle)
        await db.flush()

        with patch(
            "backend.modules.chess_intelligence.service.get_puzzle_provider"
        ) as provider_cls:
            resp = await ChessCatalogService(db).get_daily_puzzle(tenant_id=tenant_id)
        assert resp.external_id == "daily-stale"
        assert resp.is_stale is True
        assert resp.freshness == "stale"
        assert resp.daily_utc == "2020-01-01"
        provider_cls.assert_not_called()

    asyncio.run(_run())


def test_daily_puzzle_sync_updates_local_then_stale_fallback() -> None:
    """§30: background sync writes local daily; later GET stays local when stale."""

    async def _run() -> None:
        from backend.modules.chess_intelligence.providers.dtos import ExternalChessPuzzle

        db = await _catalog_session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()

        external = ExternalChessPuzzle(
            provider="lichess_puzzles",
            external_id="daily-sync-1",
            starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            solution_moves_uci=["e2e4"],
            solution_moves_san=["e4"],
            rating=1200,
            themes=["opening"],
        )
        mock_provider = AsyncMock()
        mock_provider.get_daily_puzzle = AsyncMock(return_value=external)

        with patch(
            "backend.modules.chess_intelligence.service.get_puzzle_provider",
            return_value=mock_provider,
        ):
            synced = await ChessCatalogService(db).sync_daily_puzzle(tenant_id=tenant_id)
        await db.commit()
        assert synced.external_id == "daily-sync-1"
        assert synced.is_stale is False
        mock_provider.get_daily_puzzle.assert_awaited()

        # GET after sync: local-first, no provider.
        with patch(
            "backend.modules.chess_intelligence.service.get_puzzle_provider"
        ) as provider_cls:
            fresh = await ChessCatalogService(db).get_daily_puzzle(tenant_id=tenant_id)
        assert fresh.external_id == "daily-sync-1"
        assert fresh.is_stale is False
        provider_cls.assert_not_called()

        # Force stale metadata day → still returned without provider.
        row = (
            await db.execute(
                select(ChessPuzzle).where(ChessPuzzle.external_id == "daily-sync-1")
            )
        ).scalar_one()
        meta = dict(row.source_metadata or {})
        meta["daily_utc"] = "2020-01-01"
        row.source_metadata = meta
        await db.commit()

        with patch(
            "backend.modules.chess_intelligence.service.get_puzzle_provider"
        ) as provider_cls:
            stale = await ChessCatalogService(db).get_daily_puzzle(tenant_id=tenant_id)
        assert stale.external_id == "daily-sync-1"
        assert stale.is_stale is True
        assert stale.freshness == "stale"
        provider_cls.assert_not_called()

    asyncio.run(_run())

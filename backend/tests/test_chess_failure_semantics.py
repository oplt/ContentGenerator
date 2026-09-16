"""§29 — remote/engine failures isolated; local catalog stays intact."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from sqlalchemy import Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.analysis_service import ChessAnalysisService
from backend.modules.chess_intelligence.catalog_queries import (
    GameSearchFilters,
    PuzzleSearchFilters,
)
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.engine.stockfish import ChessEngineConfigError
from backend.modules.chess_intelligence.failure_semantics import (
    CATALOG_PRESERVATION_GUARANTEE,
    FAILURE_RULES,
    catalog_survives_remote_outage,
)
from backend.modules.chess_intelligence.importers import (
    PgnArchiveImportConfig,
    PgnArchiveImporter,
)
from backend.modules.chess_intelligence.ingestion_mode import (
    ChessIngestionMode,
    stamp_ingestion_mode,
)
from backend.modules.chess_intelligence.models import (
    ChessAnalysisJob,
    ChessAnalysisJobStatus,
    ChessContentOpportunityScore,
    ChessCriticalMoment,
    ChessGame,
    ChessGameSource,
    ChessPositionAnalysis,
    ChessPuzzle,
    ChessTacticalPattern,
)
from backend.modules.chess_intelligence.normalizer import (
    chess_game_from_parsed,
    chess_puzzle_from_fields,
)
from backend.modules.chess_intelligence.provider_sync_state import (
    ChessProviderSyncState,
    ChessProviderSyncStateService,
)
from backend.modules.chess_intelligence.service import ChessCatalogService
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

_GOOD = """
[Event "Good"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
"""

_EMPTY = """
[Event "Empty"]
[White "X"]
[Black "Y"]
[Result "*"]

*
"""


async def _catalog_session(*extra: Table) -> AsyncSession:
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

    tables = [Tenant.__table__, ChessGame.__table__, ChessGameSource.__table__, *extra]
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=cast(list[Table], tables)
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_failure_semantics_contract() -> None:
    assert catalog_survives_remote_outage() is True
    assert "delete" in CATALOG_PRESERVATION_GUARANTEE.lower()
    failures = {r.failure for r in FAILURE_RULES}
    assert failures == {
        "lichess_unavailable",
        "daily_puzzle_provider_unavailable",
        "provider_sync_fails",
        "stockfish_unavailable",
        "malformed_archive_pgn",
    }


def test_list_games_survives_provider_outage() -> None:
    async def _run() -> None:
        db = await _catalog_session(ChessPuzzle.__table__)
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        parsed = parse_chess_input(_GOOD, "pgn")
        game = chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed)
        game.is_famous = True
        game.famous_title = "Local Classic"
        await ChessGameDedupeService(db).upsert_game(
            game=game,
            source=SourceRef(provider="pgn_archive", external_id="1"),
        )
        puzzle = chess_puzzle_from_fields(
            tenant_id=tenant_id,
            external_id="p-local",
            provider="lichess_puzzles",
            starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            solution_moves_uci=["e2e4"],
            solution_moves_san=["e4"],
            rating=1400,
            themes=["opening"],
        )
        puzzle.id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        puzzle.created_at = now
        puzzle.updated_at = now
        db.add(puzzle)
        await db.commit()

        svc = ChessCatalogService(db)
        page = await svc.list_games(
            tenant_id=tenant_id,
            filters=GameSearchFilters(),
            limit=50,
            cursor=None,
        )
        assert len(page.items) >= 1
        assert page.items[0].white_player == "A"

        famous = await svc.list_games(
            tenant_id=tenant_id,
            filters=GameSearchFilters(famous_only=True),
            limit=50,
            cursor=None,
        )
        assert len(famous.items) >= 1
        assert all(g.is_famous for g in famous.items)

        puzzles = await svc.list_puzzles(
            tenant_id=tenant_id,
            filters=PuzzleSearchFilters(),
            limit=50,
            cursor=None,
        )
        assert len(puzzles.items) >= 1
        assert puzzles.items[0].external_id == "p-local"

    asyncio.run(_run())


def test_stale_daily_puzzle_returned_without_provider() -> None:
    async def _run() -> None:
        db = await _catalog_session(ChessPuzzle.__table__)
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        puzzle = chess_puzzle_from_fields(
            tenant_id=tenant_id,
            external_id="old-daily",
            provider="lichess_puzzles",
            starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            solution_moves_uci=["e2e4"],
            solution_moves_san=["e4"],
            source_metadata=stamp_ingestion_mode(
                {"daily_utc": "2020-01-01", "via": "daily_puzzle_sync"},
                ChessIngestionMode.PUZZLE_SYNC,
            ),
            retrieved_at=now,
        )
        puzzle.id = uuid.uuid4()
        puzzle.created_at = now
        puzzle.updated_at = now
        db.add(puzzle)
        await db.commit()

        resp = await ChessCatalogService(db).get_daily_puzzle(tenant_id=tenant_id)
        assert resp.external_id == "old-daily"
        assert resp.is_stale is True

    asyncio.run(_run())


def test_sync_failure_keeps_high_water_mark() -> None:
    async def _run() -> None:
        db = await _catalog_session(ChessProviderSyncState.__table__)
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        svc = ChessProviderSyncStateService(db)
        state = await svc.get_or_create(
            tenant_id=tenant_id, provider="lichess_masters", params={}
        )
        await svc.mark_success(state, job_id=uuid.uuid4())
        mark = state.high_water_mark
        assert mark is not None
        await svc.mark_failure(state, job_id=uuid.uuid4(), error_summary="provider down")
        assert state.high_water_mark == mark
        assert state.last_error_summary == "provider down"

    asyncio.run(_run())


def test_malformed_pgn_tracked_and_import_continues(tmp_path: Path) -> None:
    async def _run() -> None:
        db = await _catalog_session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        archive = tmp_path / "mixed.pgn"
        archive.write_text(_EMPTY + "\n\n" + _GOOD, encoding="utf-8")

        progress = await PgnArchiveImporter(db).run(
            PgnArchiveImportConfig(
                tenant_id=tenant_id,
                file_path=archive,
                provider="pgn_archive",
                source_name="mixed",
            )
        )
        await db.commit()
        assert progress.skipped_error >= 1
        assert progress.inserted >= 1
        games = (await db.execute(select(ChessGame))).scalars().all()
        assert len(games) >= 1

    asyncio.run(_run())


def test_stockfish_failure_marks_job_failed_game_intact() -> None:
    async def _run() -> None:
        db = await _catalog_session(
            ChessAnalysisJob.__table__,
            ChessPositionAnalysis.__table__,
            ChessCriticalMoment.__table__,
            ChessTacticalPattern.__table__,
            ChessContentOpportunityScore.__table__,
        )
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        parsed = parse_chess_input(_GOOD, "pgn")
        upsert = await ChessGameDedupeService(db).upsert_game(
            game=chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed),
            source=SourceRef(provider="manual", external_id="sf-fail"),
        )
        await db.commit()
        game_id = upsert.game.id

        def _boom() -> None:
            raise ChessEngineConfigError("stockfish binary missing")

        svc = ChessAnalysisService(db, engine_factory=_boom)  # type: ignore[arg-type]
        enqueued = await svc.enqueue(
            tenant_id=tenant_id,
            user_id=None,
            game_id=game_id,
        )
        await db.commit()
        done = await svc.process_job(tenant_id=tenant_id, job_id=enqueued.job.id)
        await db.commit()

        assert done.status == ChessAnalysisJobStatus.FAILED.value
        assert "stockfish" in (done.error_message or "").lower()
        still = await db.get(ChessGame, game_id)
        assert still is not None
        assert still.deleted_at is None
        page = await ChessCatalogService(db).list_games(
            tenant_id=tenant_id,
            filters=GameSearchFilters(),
            limit=50,
            cursor=None,
        )
        assert any(g.id == game_id for g in page.items)

    asyncio.run(_run())

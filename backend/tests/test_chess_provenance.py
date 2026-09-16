"""Phase 19 — source provenance: provider → catalog → video trace."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast
from unittest.mock import MagicMock

from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.licenses import license_for_provider
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource, ChessPuzzle
from backend.modules.chess_intelligence.normalizer import (
    chess_game_from_parsed,
    chess_puzzle_from_fields,
)
from backend.modules.chess_intelligence.provenance_service import ChessProvenanceService
from backend.modules.chess_video.models import ChessVideoJob, ChessVideoJobStatus
from backend.modules.chess_video.schemas import ChessVideoCreateRequest
from backend.modules.chess_video.service import ChessVideoService
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

_PGN = """
[Event "Test"]
[White "Alpha"]
[Black "Beta"]
[Date "2000.01.01"]
[Result "1-0"]

1. e4 e5 2. Nf3 1-0
"""


async def _session(*extra: Table) -> AsyncSession:
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

    tables = [
        Tenant.__table__,
        ChessGame.__table__,
        ChessGameSource.__table__,
        ChessPuzzle.__table__,
        ChessVideoJob.__table__,
        *extra,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=cast(list[Table], tables)
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_license_for_known_providers() -> None:
    assert "lichess" in (license_for_provider("lichess_masters") or "").lower()
    assert license_for_provider("unknown_xyz") is None


def test_game_provenance_lists_sources_and_pgn() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        parsed = parse_chess_input(_PGN, "pgn")
        game = chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed)
        outcome = await ChessGameDedupeService(db).upsert_game(
            game=game,
            source=SourceRef(
                provider="lichess_masters",
                external_id="m1",
                source_url="https://example.test/m1",
                license_note=license_for_provider("lichess_masters"),
                import_batch_id="batch-1",
            ),
        )
        await ChessGameDedupeService(db).upsert_game(
            game=chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed),
            source=SourceRef(provider="pgn_archive", source_name="archive.pgn"),
        )
        await db.commit()

        trace = await ChessProvenanceService(db).for_game(
            tenant_id=tenant_id, game_id=outcome.game.id
        )
        assert trace.entity_type == "chess_game"
        assert "e4" in trace.normalized_pgn
        assert trace.primary_source is not None
        assert trace.primary_source.provider == "lichess_masters"
        assert trace.primary_source.license_note
        assert len(trace.sources) == 2
        assert "authoritative" in trace.evidence_note.lower()

    asyncio.run(_run())


def test_puzzle_provenance_fields() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        puzzle = chess_puzzle_from_fields(
            tenant_id=tenant_id,
            external_id="p1",
            provider="lichess_puzzles",
            starting_fen="8/8/8/8/8/8/4P3/4K2k w - - 0 1",
            solution_moves_uci=["e2e4"],
            solution_moves_san=["e4"],
            import_batch_id="b-puzzles",
            license_note=license_for_provider("lichess_puzzles"),
        )
        db.add(puzzle)
        await db.commit()

        trace = await ChessProvenanceService(db).for_puzzle(
            tenant_id=tenant_id, puzzle_id=puzzle.id
        )
        assert trace.provider == "lichess_puzzles"
        assert trace.import_batch_id == "b-puzzles"
        assert trace.license_note
        assert trace.solution_moves_uci == ["e2e4"]

    asyncio.run(_run())


def test_video_provenance_links_catalog_game() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        parsed = parse_chess_input(_PGN, "pgn")
        game = chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed)
        outcome = await ChessGameDedupeService(db).upsert_game(
            game=game,
            source=SourceRef(provider="manual", external_id="v1"),
        )
        await db.commit()

        svc = ChessVideoService(db)
        svc._enqueue = MagicMock()  # type: ignore[method-assign]
        job = await svc.create(
            tenant_id=tenant_id,
            user_id=None,
            payload=ChessVideoCreateRequest(chess_game_id=outcome.game.id),
        )
        await db.commit()
        assert job.chess_game_id == outcome.game.id
        assert job.status == ChessVideoJobStatus.QUEUED.value

        trace = await ChessProvenanceService(db).for_video(
            tenant_id=tenant_id, job_id=job.id
        )
        assert trace.chess_game_id == outcome.game.id
        assert trace.game is not None
        assert trace.game.normalized_pgn
        assert trace.normalized_pgn

    asyncio.run(_run())


def test_provenance_routes_registered() -> None:
    from backend.api.router import api_router

    paths = {getattr(r, "path", "") for r in api_router.routes}
    assert "/api/v1/chess/games/{game_id}/provenance" in paths
    assert "/api/v1/chess/puzzles/{puzzle_id}/provenance" in paths
    assert "/api/v1/chess-videos/{job_id}/provenance" in paths

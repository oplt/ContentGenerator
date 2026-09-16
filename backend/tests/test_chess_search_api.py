"""Phase 10 — chess catalog search API."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast

from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.catalog_queries import (
    ChessCatalogQuery,
    GameSearchFilters,
    PuzzleSearchFilters,
)
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource, ChessPuzzle
from backend.modules.chess_intelligence.normalizer import chess_puzzle_from_fields
from backend.modules.chess_intelligence.schemas import ChessGameImportRequest
from backend.modules.chess_intelligence.service import ChessCatalogService
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.identity_access.models import Tenant

_PGN_A = """
[Event "World Ch"]
[White "Kasparov"]
[Black "Topalov"]
[Date "1999.01.01"]
[Result "1-0"]
[ECO "B07"]
[Opening "Pirc"]

1. e4 d6 2. d4 1-0
"""

_PGN_B = """
[Event "Online"]
[White "Carlsen"]
[Black "Nakamura"]
[Date "2020.05.01"]
[Result "1/2-1/2"]
[ECO "C65"]

1. e4 e5 2. Nf3 1/2-1/2
"""


async def _session() -> AsyncSession:
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
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(
                    list[Table],
                    [
                        Tenant.__table__,
                        ChessGame.__table__,
                        ChessGameSource.__table__,
                        ChessPuzzle.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


async def _seed_games(db: AsyncSession, tenant_id: uuid.UUID) -> list[ChessGame]:
    games: list[ChessGame] = []
    for pgn, famous, tags, provider in (
        (_PGN_A, True, ["immortal"], "pgn_archive"),
        (_PGN_B, False, [], "chesscom"),
    ):
        parsed = parse_chess_input(pgn, "pgn")
        game = chess_game_from_parsed(
            tenant_id=tenant_id,
            parsed=parsed,
            source_provider=provider,
        )
        game.is_famous = famous
        game.famous_title = "Immortal" if famous else None
        game.historical_tags = tags
        game.white_rating = 2800 if famous else 2800
        game.black_rating = 2700 if famous else 2750
        outcome = await ChessGameDedupeService(db).upsert_game(
            game=game,
            source=SourceRef(provider=provider, external_id=game.game_fingerprint[:12]),
        )
        games.append(outcome.game)
    await db.commit()
    return games


def test_search_filters_pagination_import_moves() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        games = await _seed_games(db, tenant_id)
        svc = ChessCatalogService(db)

        page = await svc.list_games(
            tenant_id=tenant_id,
            filters=GameSearchFilters(player="kasparov", famous_only=True),
            limit=10,
            cursor=None,
        )
        assert len(page.items) == 1
        assert page.items[0].white_player == "Kasparov"
        assert page.has_more is False

        eco = await svc.list_games(
            tenant_id=tenant_id,
            filters=GameSearchFilters(eco="B07"),
            limit=10,
            cursor=None,
        )
        assert len(eco.items) == 1

        tagged = await svc.list_games(
            tenant_id=tenant_id,
            filters=GameSearchFilters(tag="immortal"),
            limit=10,
            cursor=None,
        )
        assert len(tagged.items) == 1

        page1 = await svc.list_games(
            tenant_id=tenant_id,
            filters=GameSearchFilters(),
            limit=1,
            cursor=None,
        )
        assert len(page1.items) == 1
        assert page1.has_more is True
        assert page1.next_cursor
        page2 = await svc.list_games(
            tenant_id=tenant_id,
            filters=GameSearchFilters(),
            limit=1,
            cursor=page1.next_cursor,
        )
        assert len(page2.items) == 1
        assert page1.items[0].id != page2.items[0].id
        assert page2.has_more is False

        detail = await svc.get_game(tenant_id=tenant_id, game_id=games[0].id)
        assert detail.id == games[0].id
        moves = await svc.get_game_moves(tenant_id=tenant_id, game_id=games[0].id)
        assert len(moves) >= 2
        assert moves[0].uci == "e2e4"

        imported = await svc.import_game(
            tenant_id=tenant_id,
            payload=ChessGameImportRequest(pgn=_PGN_B, provider="manual"),
        )
        assert imported.created_game is False  # fingerprint already present
        assert imported.created_source is True

        famous = await svc.list_games(
            tenant_id=tenant_id,
            filters=GameSearchFilters(famous_only=True),
            limit=10,
            cursor=None,
        )
        assert all(item.is_famous for item in famous.items)

        puzzle = chess_puzzle_from_fields(
            tenant_id=tenant_id,
            external_id="p1",
            provider="lichess_puzzles",
            starting_fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            solution_moves_uci=["e7e5"],
            solution_moves_san=["e5"],
            rating=1500,
            popularity=80,
            themes=["opening"],
            opening_tags=["Kings_Pawn"],
        )
        db.add(puzzle)
        await db.commit()

        puzzles = await svc.list_puzzles(
            tenant_id=tenant_id,
            filters=PuzzleSearchFilters(min_rating=1400, theme="opening"),
            limit=10,
            cursor=None,
        )
        assert len(puzzles.items) == 1
        got = await svc.get_puzzle(tenant_id=tenant_id, puzzle_id=puzzle.id)
        assert got.external_id == "p1"

        # Query layer limit clamp
        q = ChessCatalogQuery(db)
        big = await q.search_games(
            tenant_id=tenant_id, filters=GameSearchFilters(), limit=500, cursor=None
        )
        assert len(big.items) <= 100

    asyncio.run(_run())


def test_router_mounted() -> None:
    from backend.api.router import api_router

    paths = {getattr(r, "path", "") for r in api_router.routes}
    assert "/api/v1/chess/games" in paths
    assert "/api/v1/chess/games/famous" in paths
    assert "/api/v1/chess/puzzles/daily" in paths

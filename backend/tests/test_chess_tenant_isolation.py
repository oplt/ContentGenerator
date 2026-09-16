"""Phase 25 — tenant isolation for chess catalog reads."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast

from fastapi import HTTPException
from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.models import ChessGame, ChessPuzzle
from backend.modules.chess_intelligence.normalizer import (
    chess_game_from_parsed,
    chess_puzzle_from_fields,
)
from backend.modules.chess_intelligence.service import ChessCatalogService
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

_PGN = """
[Event "T"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
"""


async def _session() -> AsyncSession:
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
                    [Tenant.__table__, ChessGame.__table__, ChessPuzzle.__table__],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_get_game_rejects_other_tenant() -> None:
    async def _run() -> None:
        db = await _session()
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        db.add_all(
            [
                Tenant(id=t1, name="A", slug=f"a-{t1.hex[:8]}"),
                Tenant(id=t2, name="B", slug=f"b-{t2.hex[:8]}"),
            ]
        )
        parsed = parse_chess_input(_PGN, "pgn")
        game = chess_game_from_parsed(tenant_id=t1, parsed=parsed)
        db.add(game)
        await db.commit()

        svc = ChessCatalogService(db)
        ok = await svc.get_game(tenant_id=t1, game_id=game.id)
        assert ok.id == game.id
        try:
            await svc.get_game(tenant_id=t2, game_id=game.id)
            raise AssertionError("expected 404")
        except HTTPException as exc:
            assert exc.status_code == 404

        moves_ok = await svc.get_game_moves(tenant_id=t1, game_id=game.id)
        assert moves_ok
        try:
            await svc.get_game_moves(tenant_id=t2, game_id=game.id)
            raise AssertionError("expected 404")
        except HTTPException as exc:
            assert exc.status_code == 404
        await db.close()

    asyncio.run(_run())


def test_get_puzzle_rejects_other_tenant() -> None:
    async def _run() -> None:
        db = await _session()
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        db.add_all(
            [
                Tenant(id=t1, name="A", slug=f"a-{t1.hex[:8]}"),
                Tenant(id=t2, name="B", slug=f"b-{t2.hex[:8]}"),
            ]
        )
        puzzle = chess_puzzle_from_fields(
            tenant_id=t1,
            external_id="iso-1",
            provider="lichess_puzzles",
            starting_fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            solution_moves_uci=["e7e5"],
            solution_moves_san=["e5"],
        )
        db.add(puzzle)
        await db.commit()

        svc = ChessCatalogService(db)
        assert (await svc.get_puzzle(tenant_id=t1, puzzle_id=puzzle.id)).id == puzzle.id
        try:
            await svc.get_puzzle(tenant_id=t2, puzzle_id=puzzle.id)
            raise AssertionError("expected 404")
        except HTTPException as exc:
            assert exc.status_code == 404
        await db.close()

    asyncio.run(_run())

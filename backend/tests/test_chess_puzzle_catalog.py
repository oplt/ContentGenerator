"""§19 — puzzles stay on ChessPuzzle; separate from historical game storage."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import cast

from sqlalchemy import Table, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.importers import (
    LichessPuzzleDatasetImporter,
    LichessPuzzleImportConfig,
)
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource, ChessPuzzle
from backend.modules.chess_intelligence.puzzle_catalog import (
    PUZZLE_INGESTION_FILTERS,
    clamp_puzzle_import_limit,
    puzzle_filters_from_params,
    puzzle_import_creates_games,
    puzzle_passes_filters,
)
from backend.modules.identity_access.models import Tenant

_HEADER = (
    "PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,"
    "OpeningTags,DailyDate\n"
)
_FEN0 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
_ROW_A = (
    f"puzA,{_FEN0},e2e4 e7e5,1500,80,90,1000,opening short,"
    "https://lichess.org/abc123xy/black#2,Kings_Pawn,2024-01-02\n"
)
_ROW_B = (
    f"puzB,{_FEN0},e2e4 e7e5 g1f3,1800,75,40,200,fork middlegame,"
    "https://lichess.org/def456zw,#4,Sicilian,2020-05-01\n"
)


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


def test_puzzle_filters_cover_prompt_dimensions() -> None:
    assert PUZZLE_INGESTION_FILTERS == frozenset(
        {
            "rating",
            "themes",
            "popularity",
            "opening",
            "date",
            "source",
            "maximum_records",
        }
    )
    assert puzzle_import_creates_games() is False


def test_opening_and_date_filters() -> None:
    f = puzzle_filters_from_params(
        {
            "openings": "Kings_Pawn",
            "date_from": "2024-01-01",
            "date_to": "2024-12-31",
            "source": "lichess_puzzles",
        }
    )
    assert puzzle_passes_filters(
        rating=1500,
        popularity=90,
        themes=["opening"],
        opening_tags=["Kings_Pawn"],
        daily_date="2024-01-02",
        provider="lichess_puzzles",
        filters=f,
    )
    assert not puzzle_passes_filters(
        rating=1500,
        popularity=90,
        themes=["opening"],
        opening_tags=["Sicilian"],
        daily_date="2024-01-02",
        provider="lichess_puzzles",
        filters=f,
    )
    assert clamp_puzzle_import_limit(9_999_999) <= 5_000_000


def test_puzzle_import_does_not_create_chess_games() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        path = Path("/tmp") / f"puz_sep_{tenant_id.hex}.csv"
        path.write_text(_HEADER + _ROW_A + _ROW_B, encoding="utf-8")
        try:
            progress = await LichessPuzzleDatasetImporter(db).run(
                LichessPuzzleImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    openings=["Kings_Pawn"],
                    limit=50,
                )
            )
            assert progress.inserted == 1
            assert progress.filtered >= 1
            puzzles = (
                await db.execute(select(func.count()).select_from(ChessPuzzle))
            ).scalar_one()
            games = (
                await db.execute(select(func.count()).select_from(ChessGame))
            ).scalar_one()
            assert puzzles == 1
            assert games == 0
            row = (await db.execute(select(ChessPuzzle))).scalar_one()
            assert row.source_game_id == "abc123xy"
        finally:
            path.unlink(missing_ok=True)
            await db.close()

    asyncio.run(_run())

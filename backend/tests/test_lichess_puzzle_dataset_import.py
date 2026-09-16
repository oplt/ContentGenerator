"""Phase 8 — streaming Lichess puzzle CSV / .zst import."""

from __future__ import annotations

import asyncio
import io
import uuid
from pathlib import Path
from typing import cast

import zstandard as zstd
from sqlalchemy import Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.importers import (
    LichessPuzzleDatasetImporter,
    LichessPuzzleImportConfig,
    iter_puzzle_csv_rows,
    open_puzzle_csv,
    row_to_player_puzzle,
)
from backend.modules.chess_intelligence.models import ChessPuzzle
from backend.modules.chess_video.parser import ChessParseError
from backend.modules.identity_access.models import Tenant

_HEADER = (
    "PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags\n"
)
# Start pos: opp e2e4 → player e7e5 (+ optional g1f3 as second solution ply)
_FEN0 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
_ROW_A = (
    f"puzA,{_FEN0},e2e4 e7e5,1500,80,90,1000,opening short,"
    "https://lichess.org/abc123xy/black#2,Kings_Pawn\n"
)
_ROW_B = (
    f"puzB,{_FEN0},e2e4 e7e5 g1f3,1800,75,40,200,fork middlegame,"
    "https://lichess.org/def456zw,#4,\n"
)
_ROW_C = (
    f"puzC,{_FEN0},e2e4 d7d5,900,90,95,5000,mate mateIn1,"
    "https://lichess.org/ghi789uv,#2,\n"
)
_ROW_BAD = f"bad1,{_FEN0},e2e4 z9z9,1200,80,50,10,opening,https://lichess.org/x,#2,\n"
_CSV = _HEADER + _ROW_A + _ROW_B + _ROW_C + _ROW_A  # trailing dupe id in-file


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
                tables=cast(list[Table], [Tenant.__table__, ChessPuzzle.__table__]),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_row_to_player_puzzle_strips_opponent_move() -> None:
    row = next(iter_puzzle_csv_rows(io.StringIO(_HEADER + _ROW_A)))
    fields = row_to_player_puzzle(row)
    assert fields["external_id"] == "puzA"
    assert fields["solution_moves_uci"] == ["e7e5"]
    assert fields["solution_moves_san"] == ["e5"]
    assert fields["starting_fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b")
    assert fields["source_game_id"] == "abc123xy"
    assert fields["rating"] == 1500
    assert fields["source_metadata"]["opponent_move_uci"] == "e2e4"


def test_row_rejects_illegal_uci() -> None:
    row = next(iter_puzzle_csv_rows(io.StringIO(_HEADER + _ROW_BAD)))
    try:
        row_to_player_puzzle(row)
        raise AssertionError("expected ChessParseError")
    except ChessParseError:
        pass


def test_open_zst_streams() -> None:
    path = Path("/tmp") / f"puzzles_{uuid.uuid4().hex}.csv.zst"
    path.write_bytes(zstd.ZstdCompressor().compress(_CSV.encode("utf-8")))
    try:
        with open_puzzle_csv(path) as stream:
            rows = list(iter_puzzle_csv_rows(stream))
        assert len(rows) == 4
        assert rows[0]["PuzzleId"] == "puzA"
    finally:
        path.unlink(missing_ok=True)


def test_import_filters_limit_idempotent() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        path = Path("/tmp") / f"puzzles_{tenant_id.hex}.csv"
        path.write_text(_CSV, encoding="utf-8")
        try:
            progress = await LichessPuzzleDatasetImporter(db).run(
                LichessPuzzleImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    batch_size=2,
                    min_rating=1000,
                    themes=["opening"],
                )
            )
            # puzA matches opening+rating; puzB fork only; puzC rating ok but mate; bad skipped
            # in-file second puzA → duplicate after first selected
            assert progress.inserted == 1
            assert progress.filtered >= 1

            again = await LichessPuzzleDatasetImporter(db).run(
                LichessPuzzleImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    min_rating=1000,
                    themes=["opening"],
                )
            )
            assert again.inserted == 0
            assert again.skipped_duplicate >= 1

            limited = await LichessPuzzleDatasetImporter(db).run(
                LichessPuzzleImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    limit=1,
                    dry_run=True,
                )
            )
            assert limited.inserted + limited.skipped_duplicate == 1

            rows = (
                await db.execute(
                    select(ChessPuzzle).where(ChessPuzzle.tenant_id == tenant_id)
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].external_id == "puzA"
            assert rows[0].provider == "lichess_puzzles"
            assert rows[0].solution_moves_uci == ["e7e5"]
        finally:
            path.unlink(missing_ok=True)

    asyncio.run(_run())


def test_dry_run_no_writes() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        path = Path("/tmp") / f"puzzles_dry_{tenant_id.hex}.csv"
        path.write_text(_HEADER + _ROW_B, encoding="utf-8")
        try:
            progress = await LichessPuzzleDatasetImporter(db).run(
                LichessPuzzleImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    dry_run=True,
                )
            )
            assert progress.inserted == 1
            count = (
                await db.execute(
                    select(ChessPuzzle).where(ChessPuzzle.tenant_id == tenant_id)
                )
            ).scalars().all()
            assert count == []
        finally:
            path.unlink(missing_ok=True)

    asyncio.run(_run())

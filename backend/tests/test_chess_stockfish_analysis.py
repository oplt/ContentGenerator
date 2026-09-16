"""Phase 14 — Stockfish engine analysis (fake engine; no binary required)."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast

import chess
import chess.engine
from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.analysis_service import ChessAnalysisService
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.engine.analyzer import analyze_game
from backend.modules.chess_intelligence.engine.base import (
    EngineLimit,
    EngineScore,
    PositionEngineResult,
)
from backend.modules.chess_intelligence.engine.scores import score_delta, score_from_pov
from backend.modules.chess_intelligence.models import (
    ChessAnalysisJob,
    ChessAnalysisJobStatus,
    ChessContentOpportunityScore,
    ChessCriticalMoment,
    ChessGame,
    ChessGameSource,
    ChessPositionAnalysis,
    ChessTacticalPattern,
)
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

_PGN = """
[Event "Test"]
[White "Alpha"]
[Black "Beta"]
[Result "1-0"]

1. e4 e5 2. Nf3 1-0
"""


class FakeEngine:
    name = "FakeFish"
    version = "0"

    def __init__(self) -> None:
        self.calls = 0

    def analyse(self, board: chess.Board, limit: EngineLimit) -> PositionEngineResult:
        self.calls += 1
        # Deterministic: prefer e2e4 / e7e5 style when legal, else first legal.
        legal = list(board.legal_moves)
        move = legal[0] if legal else None
        for candidate in legal:
            if candidate.uci() in {"e2e4", "e7e5", "g1f3"}:
                move = candidate
                break
        cp = 20 - self.calls * 5
        return PositionEngineResult(
            fen=board.fen(),
            score=EngineScore(cp=cp),
            best_move_uci=move.uci() if move else None,
            best_move_san=board.san(move) if move else None,
            depth=limit.depth or 1,
            nodes=10,
            engine_name=self.name,
            engine_version=self.version,
        )

    def close(self) -> None:
        return None


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
                    [
                        Tenant.__table__,
                        ChessGame.__table__,
                        ChessGameSource.__table__,
                        ChessAnalysisJob.__table__,
                        ChessPositionAnalysis.__table__,
                        ChessCriticalMoment.__table__,
                        ChessTacticalPattern.__table__,
                        ChessContentOpportunityScore.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_score_delta_skips_mate() -> None:
    assert score_delta(EngineScore(cp=50), EngineScore(cp=-20)) == -70
    assert score_delta(EngineScore(mate=3), EngineScore(cp=100)) is None
    pov = chess.engine.PovScore(chess.engine.Cp(35), chess.WHITE)
    assert score_from_pov(pov).cp == 35


def test_analyze_game_with_fake_engine() -> None:
    parsed = parse_chess_input(_PGN, "pgn")
    engine = FakeEngine()
    plies = analyze_game(parsed, engine, depth=4, time_seconds=None)
    assert len(plies) == 3
    assert plies[0].played_move_uci == "e2e4"
    assert plies[0].best_move_uci is not None
    assert plies[0].evaluation_delta is not None
    assert engine.calls == 4  # start + after each move


def test_analysis_service_process_job() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        parsed = parse_chess_input(_PGN, "pgn")
        game = chess_game_from_parsed(
            tenant_id=tenant_id, parsed=parsed, source_provider="manual"
        )
        outcome = await ChessGameDedupeService(db).upsert_game(
            game=game,
            source=SourceRef(provider="manual", external_id="sf1"),
        )
        await db.commit()
        fake = FakeEngine()
        svc = ChessAnalysisService(db, engine_factory=lambda: fake)
        job = await svc.enqueue(
            tenant_id=tenant_id,
            user_id=None,
            game_id=outcome.game.id,
        )
        await db.commit()
        done = await svc.process_job(tenant_id=tenant_id, job_id=job.id)
        await db.commit()
        assert done.status == ChessAnalysisJobStatus.COMPLETED.value
        assert done.ply_count == 3
        resp = await svc.get_job(tenant_id=tenant_id, job_id=job.id)
        assert len(resp.positions) == 3
        assert resp.positions[0].played_move_san
        assert isinstance(resp.critical_moments, list)
        assert isinstance(resp.tactical_patterns, list)
        assert resp.content_opportunity is not None
        assert resp.content_opportunity.score == sum(resp.content_opportunity.components.values())
        assert resp.content_opportunity.persisted is True

    asyncio.run(_run())

"""§12 — versioned Stockfish analysis reuse via analysis_fingerprint."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast

from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.analysis_fingerprint import (
    ANALYSIS_SCHEMA_VERSION,
    compute_analysis_fingerprint,
    normalize_analysis_settings,
)
from backend.modules.chess_intelligence.analysis_service import ChessAnalysisService
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
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
from backend.modules.chess_intelligence.schemas import ChessAnalysisRequest
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

_PGN = """
[Event "Test"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
"""


def test_fingerprint_stable_and_settings_sensitive() -> None:
    base = {
        "depth": 12,
        "time_limit_seconds": None,
        "hash_mb": 64,
        "threads": 1,
        "score_perspective": "white",
        "multipv": 1,
    }
    a = compute_analysis_fingerprint(
        game_fingerprint="abc",
        engine_version="stockfish",
        analysis_settings=base,
    )
    b = compute_analysis_fingerprint(
        game_fingerprint="abc",
        engine_version="stockfish",
        analysis_settings=normalize_analysis_settings(base),
    )
    assert a == b
    deeper = compute_analysis_fingerprint(
        game_fingerprint="abc",
        engine_version="stockfish",
        analysis_settings={**base, "depth": 24},
    )
    assert deeper != a
    other_engine = compute_analysis_fingerprint(
        game_fingerprint="abc",
        engine_version="stockfish-17",
        analysis_settings=base,
    )
    assert other_engine != a
    assert ANALYSIS_SCHEMA_VERSION.startswith("chess_analysis.")


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


async def _seed_game(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
    await db.flush()
    parsed = parse_chess_input(_PGN, "pgn")
    game = chess_game_from_parsed(
        tenant_id=tenant_id, parsed=parsed, source_provider="manual"
    )
    upsert = await ChessGameDedupeService(db).upsert_game(
        game=game,
        source=SourceRef(provider="manual", external_id="reuse-1"),
    )
    await db.flush()
    return tenant_id, upsert.game.id


def test_enqueue_reuses_completed_same_fingerprint() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id, game_id = await _seed_game(db)
        svc = ChessAnalysisService(db, engine_factory=lambda: None)  # type: ignore[arg-type,return-value]
        first = await svc.enqueue(tenant_id=tenant_id, user_id=None, game_id=game_id)
        first.job.status = ChessAnalysisJobStatus.COMPLETED.value
        await db.flush()

        second = await svc.enqueue(tenant_id=tenant_id, user_id=None, game_id=game_id)
        assert second.reused is True
        assert second.should_dispatch is False
        assert second.job.id == first.job.id

        deeper = await svc.enqueue(
            tenant_id=tenant_id,
            user_id=None,
            game_id=game_id,
            payload=ChessAnalysisRequest(depth=24),
        )
        assert deeper.reused is False
        assert deeper.job.id != first.job.id
        assert deeper.job.analysis_fingerprint != first.job.analysis_fingerprint

    asyncio.run(_run())


def test_enqueue_requeues_failed_and_force_cancels() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id, game_id = await _seed_game(db)
        svc = ChessAnalysisService(db, engine_factory=lambda: None)  # type: ignore[arg-type,return-value]
        first = await svc.enqueue(tenant_id=tenant_id, user_id=None, game_id=game_id)
        first.job.status = ChessAnalysisJobStatus.FAILED.value
        first.job.error_message = "boom"
        await db.flush()

        retried = await svc.enqueue(tenant_id=tenant_id, user_id=None, game_id=game_id)
        assert retried.reused is True
        assert retried.should_dispatch is True
        assert retried.job.id == first.job.id
        assert retried.job.status == ChessAnalysisJobStatus.QUEUED.value
        assert retried.job.error_message is None

        retried.job.status = ChessAnalysisJobStatus.COMPLETED.value
        await db.flush()
        forced = await svc.enqueue(
            tenant_id=tenant_id,
            user_id=None,
            game_id=game_id,
            payload=ChessAnalysisRequest(force=True),
        )
        assert forced.reused is False
        assert forced.should_dispatch is True
        assert forced.job.id != first.job.id
        await db.refresh(first.job)
        assert first.job.status == ChessAnalysisJobStatus.CANCELLED.value

    asyncio.run(_run())


def test_integrity_error_on_insert_reuses_winner() -> None:
    """Simulated race: lookup miss then unique violation → return winner (§13)."""

    async def _run() -> None:
        from unittest.mock import AsyncMock

        db = await _session()
        tenant_id, game_id = await _seed_game(db)
        svc = ChessAnalysisService(db, engine_factory=lambda: None)  # type: ignore[arg-type,return-value]
        winner = await svc.enqueue(tenant_id=tenant_id, user_id=None, game_id=game_id)
        assert winner.reused is False

        # Pretend concurrent peer already inserted; our SELECT missed it.
        svc._find_matching_job = AsyncMock(side_effect=[None, winner.job])  # type: ignore[method-assign]
        raced = await svc.enqueue(tenant_id=tenant_id, user_id=None, game_id=game_id)
        assert raced.reused is True
        assert raced.should_dispatch is False
        assert raced.job.id == winner.job.id

    asyncio.run(_run())


def test_enqueue_keeps_prior_depth_profile_completed() -> None:
    """Depth 12 completed stays when depth 24 is enqueued (§14 history)."""

    async def _run() -> None:
        db = await _session()
        tenant_id, game_id = await _seed_game(db)
        svc = ChessAnalysisService(db, engine_factory=lambda: None)  # type: ignore[arg-type,return-value]
        shallow = await svc.enqueue(
            tenant_id=tenant_id,
            user_id=None,
            game_id=game_id,
            payload=ChessAnalysisRequest(depth=12),
        )
        shallow.job.status = ChessAnalysisJobStatus.COMPLETED.value
        await db.flush()

        deep = await svc.enqueue(
            tenant_id=tenant_id,
            user_id=None,
            game_id=game_id,
            payload=ChessAnalysisRequest(depth=24),
        )
        deep.job.status = ChessAnalysisJobStatus.COMPLETED.value
        await db.flush()

        history = await svc.list_for_game(tenant_id=tenant_id, game_id=game_id)
        assert len(history.items) == 2
        assert {row.depth for row in history.items} == {12, 24}

        preferred = await svc.select_for_game(
            tenant_id=tenant_id, game_id=game_id, profile="preferred"
        )
        assert preferred is not None
        assert preferred.depth == 24
        assert preferred.id == deep.job.id

        matched = await svc.select_for_game(
            tenant_id=tenant_id, game_id=game_id, profile="matching", depth=12
        )
        assert matched is not None
        assert matched.id == shallow.job.id
        await db.refresh(shallow.job)
        assert shallow.job.status == ChessAnalysisJobStatus.COMPLETED.value

    asyncio.run(_run())


def test_failed_reclaim_only_one_dispatcher() -> None:
    """Second concurrent FAILED reclaim loses CAS → no second Celery dispatch."""

    async def _run() -> None:
        db = await _session()
        tenant_id, game_id = await _seed_game(db)
        svc = ChessAnalysisService(db, engine_factory=lambda: None)  # type: ignore[arg-type,return-value]
        first = await svc.enqueue(tenant_id=tenant_id, user_id=None, game_id=game_id)
        first.job.status = ChessAnalysisJobStatus.FAILED.value
        first.job.error_message = "boom"
        await db.flush()

        a = await svc.enqueue(tenant_id=tenant_id, user_id=None, game_id=game_id)
        assert a.should_dispatch is True
        assert a.job.status == ChessAnalysisJobStatus.QUEUED.value
        # Concurrent loser still holds a stale FAILED view; CAS must no-op.
        b = await svc._reclaim_failed_job(
            job=a.job,
            user_id=None,
            fingerprint=a.job.analysis_fingerprint,
            tenant_id=tenant_id,
        )
        assert b.should_dispatch is False
        assert b.reused is True
        assert b.job.id == a.job.id

    asyncio.run(_run())

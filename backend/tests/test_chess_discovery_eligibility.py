"""§21 — recent discovery eligibility → optional analysis (not auto-famous)."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.analysis_service import AnalysisEnqueueOutcome
from backend.modules.chess_intelligence.catalog_job_models import ChessCatalogJob
from backend.modules.chess_intelligence.catalog_job_sync import provider_sync
from backend.modules.chess_intelligence.discovery_eligibility import (
    DiscoveryAnalysisPolicy,
    discovery_must_not_set_famous,
    evaluate_analysis_eligibility,
    policy_from_params,
)
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource
from backend.modules.chess_intelligence.provider_sync_state import ChessProviderSyncState
from backend.modules.chess_intelligence.providers.dtos import (
    ExternalChessGame,
    ExternalChessGameSummary,
)
from backend.modules.identity_access.models import Tenant

_PGN_HIGH = """
[Event "Candidates"]
[White "Carlsen, M"]
[Black "Nepomniachtchi"]
[WhiteElo "2850"]
[BlackElo "2780"]
[Result "1-0"]

1. e4 e5 1-0
"""

_PGN_LOW = """
[Event "Club"]
[White "A"]
[Black "B"]
[WhiteElo "1500"]
[BlackElo "1400"]
[Result "1-0"]

1. d4 d5 1-0
"""

def _game(**overrides: object) -> ChessGame:
    base = dict(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        white_player="Carlsen",
        black_player="Nepomniachtchi",
        white_rating=2850,
        black_rating=2780,
        event="Candidates",
        result="1-0",
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        normalized_pgn="1. e4 e5",
        move_count=2,
        content_hash="a" * 64,
        game_fingerprint="b" * 64,
        is_famous=False,
        source_metadata={},
        historical_tags=[],
    )
    base.update(overrides)
    return ChessGame(**base)  # type: ignore[arg-type]


async def _sync_session() -> AsyncSession:
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
                        ChessCatalogJob.__table__,
                        ChessProviderSyncState.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_discovery_never_sets_famous_contract() -> None:
    assert discovery_must_not_set_famous() is True


def test_auto_analyze_disabled_by_default_policy() -> None:
    policy = policy_from_params({})
    assert policy.auto_analyze is False
    decision = evaluate_analysis_eligibility(
        _game(), policy, created_game=True
    )
    assert decision.eligible is False
    assert "auto_analyze_disabled" in decision.reasons


def test_eligibility_requires_rating_and_skips_low() -> None:
    policy = DiscoveryAnalysisPolicy(auto_analyze=True, min_rating=2600)
    high = evaluate_analysis_eligibility(_game(), policy, created_game=True)
    assert high.eligible is True
    low = evaluate_analysis_eligibility(
        _game(white_rating=2200, black_rating=2100), policy, created_game=True
    )
    assert low.eligible is False
    assert "below_min_rating" in low.reasons


def test_eligibility_event_whitelist_and_new_only() -> None:
    policy = DiscoveryAnalysisPolicy(
        auto_analyze=True,
        min_rating=None,
        event_whitelist=("Candidates",),
        new_games_only=True,
    )
    assert evaluate_analysis_eligibility(
        _game(event="Candidates Tournament"), policy, created_game=True
    ).eligible
    assert not evaluate_analysis_eligibility(
        _game(event="Club night"), policy, created_game=True
    ).eligible
    assert not evaluate_analysis_eligibility(
        _game(), policy, created_game=False
    ).eligible


def test_policy_from_params_job_overrides() -> None:
    policy = policy_from_params(
        {
            "auto_analyze": True,
            "analyze_min_rating": 2500,
            "analyze_max_per_sync": 3,
            "analyze_event_whitelist": "Tata Steel, Norway Chess",
        }
    )
    assert policy.auto_analyze is True
    assert policy.min_rating == 2500
    assert policy.max_analyze_per_sync == 3
    assert "Tata Steel" in policy.event_whitelist


def test_provider_sync_default_does_not_enqueue_analysis() -> None:
    async def _run() -> None:
        db = await _sync_session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        job = ChessCatalogJob(
            tenant_id=tenant_id,
            kind="provider_sync",
            status="running",
            progress=0.0,
            params={"provider": "lichess_masters", "max_games": 1},
            result={},
            import_batch_id="batch-21",
        )
        db.add(job)
        await db.flush()

        summary = ExternalChessGameSummary(
            provider="lichess_masters",
            external_id="g-high",
            white_player="Carlsen",
            black_player="Nepo",
        )
        external = ExternalChessGame(
            provider="lichess_masters",
            external_id="g-high",
            pgn=_PGN_HIGH,
            white_player="Carlsen, M",
            black_player="Nepomniachtchi",
            white_rating=2850,
            black_rating=2780,
            result="1-0",
            event="Candidates",
        )
        mock_provider = MagicMock()
        mock_provider.search_games = AsyncMock(return_value=[summary])
        mock_provider.get_game = AsyncMock(return_value=external)

        with (
            patch(
                "backend.modules.chess_intelligence.catalog_job_sync.get_historical_game_provider",
                return_value=mock_provider,
            ),
            patch(
                "backend.modules.chess_intelligence.catalog_job_sync.ChessAnalysisService"
            ) as svc_cls,
        ):
            result = await provider_sync(db, job)

        svc_cls.assert_not_called()
        assert result.get("auto_analyze") is False
        assert result.get("sets_famous") is False
        assert "analysis_requested" not in result or result.get("analysis_requested", 0) == 0
        game = (await db.execute(select(ChessGame))).scalar_one()
        assert game.is_famous is False

    asyncio.run(_run())


def test_provider_sync_auto_analyze_enqueues_eligible_only() -> None:
    async def _run() -> None:
        db = await _sync_session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        job = ChessCatalogJob(
            tenant_id=tenant_id,
            kind="provider_sync",
            status="running",
            progress=0.0,
            params={
                "provider": "lichess_masters",
                "max_games": 2,
                "auto_analyze": True,
                "analyze_min_rating": 2400,
                "analyze_max_per_sync": 5,
            },
            result={},
            import_batch_id="batch-21b",
        )
        db.add(job)
        await db.flush()

        summaries = [
            ExternalChessGameSummary(
                provider="lichess_masters",
                external_id="g-high",
                white_player="Carlsen",
                black_player="Nepo",
            ),
            ExternalChessGameSummary(
                provider="lichess_masters",
                external_id="g-low",
                white_player="A",
                black_player="B",
            ),
        ]
        externals = {
            "g-high": ExternalChessGame(
                provider="lichess_masters",
                external_id="g-high",
                pgn=_PGN_HIGH,
                white_player="Carlsen, M",
                black_player="Nepomniachtchi",
                white_rating=2850,
                black_rating=2780,
                result="1-0",
                event="Candidates",
            ),
            "g-low": ExternalChessGame(
                provider="lichess_masters",
                external_id="g-low",
                pgn=_PGN_LOW,
                white_player="A",
                black_player="B",
                white_rating=1500,
                black_rating=1400,
                result="1-0",
                event="Club",
            ),
        }

        mock_provider = MagicMock()
        mock_provider.search_games = AsyncMock(return_value=summaries)
        mock_provider.get_game = AsyncMock(
            side_effect=lambda eid: externals[eid]
        )

        fake_job = MagicMock()
        fake_job.id = uuid.uuid4()
        enqueue = AsyncMock(
            return_value=AnalysisEnqueueOutcome(
                job=fake_job, reused=False, should_dispatch=True
            )
        )
        mock_svc = MagicMock()
        mock_svc.enqueue = enqueue
        mock_svc.enqueue_celery = MagicMock()

        with (
            patch(
                "backend.modules.chess_intelligence.catalog_job_sync.get_historical_game_provider",
                return_value=mock_provider,
            ),
            patch(
                "backend.modules.chess_intelligence.catalog_job_sync.ChessAnalysisService",
                return_value=mock_svc,
            ),
        ):
            result = await provider_sync(db, job)

        assert result["auto_analyze"] is True
        assert result["sets_famous"] is False
        assert result["analysis_requested"] == 1
        assert result["analysis_skipped_ineligible"] >= 1
        assert enqueue.await_count == 1
        mock_svc.enqueue_celery.assert_called_once()
        games = (await db.execute(select(ChessGame))).scalars().all()
        assert all(g.is_famous is False for g in games)

    asyncio.run(_run())

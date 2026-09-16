"""§5 — ChessProviderSyncState is durable feed state; ChessCatalogJob is one run."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.catalog_job_models import ChessCatalogJob
from backend.modules.chess_intelligence.catalog_job_sync import provider_sync
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource
from backend.modules.chess_intelligence.provider_sync_state import (
    ChessProviderSyncState,
    ChessProviderSyncStateService,
    compute_incremental_window,
    compute_query_hash,
    default_sync_key,
    game_date_in_window,
    parse_game_date,
)
from backend.modules.chess_intelligence.providers.dtos import (
    ExternalChessGame,
    ExternalChessGameSummary,
)
from backend.modules.identity_access.models import Tenant

_PGN = """
[Event "Sync"]
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


def test_sync_key_and_query_hash_stable() -> None:
    params = {"provider": "lichess_masters", "year_from": 2020, "player": "Carlsen"}
    assert default_sync_key(provider="lichess_masters", params=params) == "default"
    assert default_sync_key(
        provider="chesscom", params={"player": "Hikaru"}
    ) == "chesscom:hikaru"
    # Sliding years are not part of feed identity.
    h1 = compute_query_hash(params)
    h2 = compute_query_hash({"player": "Carlsen", "year_from": 1999})
    assert h1 == h2


def test_get_or_create_is_tenant_scoped() -> None:
    async def _run() -> None:
        db = await _session()
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        db.add(Tenant(id=t1, name="A", slug=f"a-{t1.hex[:8]}"))
        db.add(Tenant(id=t2, name="B", slug=f"b-{t2.hex[:8]}"))
        await db.flush()
        svc = ChessProviderSyncStateService(db)
        a = await svc.get_or_create(
            tenant_id=t1, provider="lichess_masters", params={"lookback_seconds": 3600}
        )
        b = await svc.get_or_create(
            tenant_id=t2, provider="lichess_masters", params={"lookback_seconds": 3600}
        )
        again = await svc.get_or_create(
            tenant_id=t1, provider="lichess_masters", params={}
        )
        assert a.id != b.id
        assert again.id == a.id
        assert a.tenant_id == t1
        assert a.lookback_seconds == 3600

    asyncio.run(_run())


def test_failure_does_not_advance_high_water_mark() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        svc = ChessProviderSyncStateService(db)
        state = await svc.get_or_create(
            tenant_id=tenant_id, provider="lichess_masters", params={}
        )
        job_id = uuid.uuid4()
        await svc.mark_success(state, job_id=job_id)
        mark = state.high_water_mark
        assert mark is not None
        await svc.mark_failure(state, job_id=uuid.uuid4(), error_summary="boom")
        assert state.high_water_mark == mark
        assert state.last_error_summary == "boom"
        assert state.last_success_at is not None

    asyncio.run(_run())


def test_incremental_window_applies_lookback_overlap() -> None:
    from datetime import datetime, timezone

    hwm = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    window = compute_incremental_window(
        high_water_mark=hwm,
        lookback_seconds=86_400,
        now=now,
    )
    assert window.bootstrap is False
    assert window.window_start == datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)
    assert window.window_end == now
    assert window.year_from == 2026
    assert window.year_to == 2026


def test_bootstrap_window_is_bounded() -> None:
    from datetime import datetime, timezone

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    window = compute_incremental_window(
        high_water_mark=None,
        lookback_seconds=86_400,
        bootstrap_lookback_seconds=2 * 86_400,
        now=now,
    )
    assert window.bootstrap is True
    assert window.window_start == datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    assert window.year_from == 2026


def test_game_date_in_window_filters() -> None:
    from datetime import datetime, timezone

    window = compute_incremental_window(
        high_water_mark=datetime(2026, 9, 15, tzinfo=timezone.utc),
        lookback_seconds=86_400,
        now=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert parse_game_date("2026.09.14") is not None
    assert game_date_in_window("2026.09.14", window=window) is True
    assert game_date_in_window("2020.01.01", window=window) is False
    assert game_date_in_window(None, window=window, keep_unknown=True) is True


def test_provider_sync_passes_window_years_to_search() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        job = ChessCatalogJob(
            tenant_id=tenant_id,
            kind="provider_sync",
            status="running",
            progress=0.0,
            params={
                "provider": "lichess_masters",
                "max_games": 1,
                "lookback_seconds": 86_400,
            },
            result={},
            import_batch_id="batch",
        )
        db.add(job)
        await db.flush()

        # Seed prior HWM so window is HWM−1d → now
        svc = ChessProviderSyncStateService(db)
        state = await svc.get_or_create(
            tenant_id=tenant_id,
            provider="lichess_masters",
            params={"lookback_seconds": 86_400},
        )
        from datetime import datetime, timezone

        state.high_water_mark = datetime(2026, 9, 15, tzinfo=timezone.utc)
        await db.flush()

        captured: dict = {}

        async def _search(query: object) -> list:
            captured["year_from"] = getattr(query, "year_from", None)
            captured["year_to"] = getattr(query, "year_to", None)
            return []

        mock_provider = MagicMock()
        mock_provider.search_games = AsyncMock(side_effect=_search)
        mock_provider.get_game = AsyncMock()

        with patch(
            "backend.modules.chess_intelligence.catalog_job_sync.get_historical_game_provider",
            return_value=mock_provider,
        ):
            result = await provider_sync(db, job)

        assert captured["year_from"] == 2026
        assert captured["year_to"] == 2026
        assert result["window"]["year_from"] == 2026
        assert result["sync_advanced"] is True
        assert result["in_window"] == 0

    asyncio.run(_run())


def test_provider_sync_advances_state_only_on_clean_run() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        job = ChessCatalogJob(
            tenant_id=tenant_id,
            kind="provider_sync",
            status="running",
            progress=0.0,
            params={"provider": "lichess_masters", "max_games": 1},
            result={},
            import_batch_id="batch",
        )
        db.add(job)
        await db.flush()

        summary = ExternalChessGameSummary(
            provider="lichess_masters",
            external_id="g1",
            white_player="A",
            black_player="B",
        )
        external = ExternalChessGame(
            provider="lichess_masters",
            external_id="g1",
            pgn=_PGN,
            white_player="A",
            black_player="B",
            result="1-0",
        )

        mock_provider = MagicMock()
        mock_provider.search_games = AsyncMock(return_value=[summary])
        mock_provider.get_game = AsyncMock(return_value=external)

        with patch(
            "backend.modules.chess_intelligence.catalog_job_sync.get_historical_game_provider",
            return_value=mock_provider,
        ):
            result = await provider_sync(db, job)

        assert result["sync_advanced"] is True
        assert result["skipped_error"] == 0
        state = (
            await db.execute(
                select(ChessProviderSyncState).where(
                    ChessProviderSyncState.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        assert state.high_water_mark is not None
        assert state.last_job_id == job.id
        assert state.last_error_summary is None

        # Second run with fetch failure must not move watermark.
        mark = state.high_water_mark
        mock_provider.get_game = AsyncMock(side_effect=RuntimeError("down"))
        with patch(
            "backend.modules.chess_intelligence.catalog_job_sync.get_historical_game_provider",
            return_value=mock_provider,
        ):
            failed = await provider_sync(db, job)
        assert failed["sync_advanced"] is False
        await db.refresh(state)
        assert state.high_water_mark == mark
        assert state.last_error_summary

    asyncio.run(_run())


def test_second_sync_resumes_and_dedupes_overlap() -> None:
    """§30 incremental sync: second run resumes HWM; overlapping ids stay one game."""

    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        job = ChessCatalogJob(
            tenant_id=tenant_id,
            kind="provider_sync",
            status="running",
            progress=0.0,
            params={"provider": "lichess_masters", "max_games": 10},
            result={},
            import_batch_id="batch-1",
        )
        db.add(job)
        await db.flush()

        pgn_a = """
[Event "A"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
"""
        pgn_b = """
[Event "B"]
[White "C"]
[Black "D"]
[Result "0-1"]

1. d4 d5 0-1
"""
        summary_a = ExternalChessGameSummary(
            provider="lichess_masters",
            external_id="ga",
            white_player="A",
            black_player="B",
        )
        summary_b = ExternalChessGameSummary(
            provider="lichess_masters",
            external_id="gb",
            white_player="C",
            black_player="D",
        )
        game_a = ExternalChessGame(
            provider="lichess_masters",
            external_id="ga",
            pgn=pgn_a,
            white_player="A",
            black_player="B",
            result="1-0",
        )
        game_b = ExternalChessGame(
            provider="lichess_masters",
            external_id="gb",
            pgn=pgn_b,
            white_player="C",
            black_player="D",
            result="0-1",
        )

        mock_provider = MagicMock()
        mock_provider.search_games = AsyncMock(return_value=[summary_a])
        mock_provider.get_game = AsyncMock(return_value=game_a)

        with patch(
            "backend.modules.chess_intelligence.catalog_job_sync.get_historical_game_provider",
            return_value=mock_provider,
        ):
            first = await provider_sync(db, job)
        assert first["sync_advanced"] is True
        assert first["inserted"] == 1
        state = (
            await db.execute(
                select(ChessProviderSyncState).where(
                    ChessProviderSyncState.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        mark_after_first = state.high_water_mark
        assert mark_after_first is not None

        # Overlap: same ga again + new gb. Search must receive window from persisted HWM.
        captured: dict = {}

        async def _search(query: object) -> list:
            captured["year_from"] = getattr(query, "year_from", None)
            return [summary_a, summary_b]

        async def _get(external_id: str) -> ExternalChessGame:
            return game_a if external_id == "ga" else game_b

        mock_provider.search_games = AsyncMock(side_effect=_search)
        mock_provider.get_game = AsyncMock(side_effect=_get)
        job.import_batch_id = "batch-2"
        with patch(
            "backend.modules.chess_intelligence.catalog_job_sync.get_historical_game_provider",
            return_value=mock_provider,
        ):
            second = await provider_sync(db, job)

        assert captured["year_from"] == mark_after_first.year
        assert second["sync_advanced"] is True
        assert second["inserted"] == 1
        assert second["skipped_duplicate"] + second["linked_source"] >= 1
        games = (
            await db.execute(select(ChessGame).where(ChessGame.tenant_id == tenant_id))
        ).scalars().all()
        assert len(games) == 2
        await db.refresh(state)
        assert state.high_water_mark is not None
        assert state.high_water_mark >= mark_after_first

    asyncio.run(_run())

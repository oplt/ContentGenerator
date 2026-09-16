"""§28 — repeated catalog ops stay idempotent (DB uniques + SAVEPOINT races)."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast
from unittest.mock import patch

from sqlalchemy import Table, event, select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.analysis_fingerprint import (
    compute_analysis_fingerprint,
    normalize_analysis_settings,
)
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.idempotency import (
    DB_IDEMPOTENCY_GUARANTEES,
    IDEMPOTENCY_OUTCOMES,
    uses_database_guarantees,
)
from backend.modules.chess_intelligence.models import (
    ChessAnalysisJob,
    ChessGame,
    ChessGameSource,
    ChessPuzzle,
)
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

_PGN = """
[Event "Idem"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
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
        *extra,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=cast(list[Table], tables)
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_idempotency_contract_lists_db_guarantees() -> None:
    assert uses_database_guarantees() is True
    assert "uq_chess_games_tenant_id_game_fingerprint" in DB_IDEMPOTENCY_GUARANTEES
    assert "uq_chess_analysis_jobs_tenant_fingerprint_active" in DB_IDEMPOTENCY_GUARANTEES
    ops = {o.operation for o in IDEMPOTENCY_OUTCOMES}
    assert "same_game_twice" in ops
    assert "same_analysis_profile_twice" in ops


def test_same_game_twice_one_row_two_sources_then_no_dupe_source() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        parsed = parse_chess_input(_PGN, "pgn")
        dedupe = ChessGameDedupeService(db)

        first = await dedupe.upsert_game(
            game=chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed),
            source=SourceRef(provider="pgn_archive", external_id="a1"),
        )
        again = await dedupe.upsert_game(
            game=chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed),
            source=SourceRef(provider="pgn_archive", external_id="a1"),
        )
        other = await dedupe.upsert_game(
            game=chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed),
            source=SourceRef(provider="lichess_masters", external_id="L1"),
        )

        assert first.created_game is True
        assert again.created_game is False and again.created_source is False
        assert other.created_game is False and other.created_source is True
        assert other.game.id == first.game.id

        games = (await db.execute(select(func.count()).select_from(ChessGame))).scalar_one()
        sources = (
            await db.execute(select(func.count()).select_from(ChessGameSource))
        ).scalar_one()
        assert games == 1
        assert sources == 2

    asyncio.run(_run())


def test_upsert_game_handles_fingerprint_integrity_race() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        parsed = parse_chess_input(_PGN, "pgn")
        winner = chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed)
        await ChessGameDedupeService(db).upsert_game(
            game=winner,
            source=SourceRef(provider="pgn_archive", external_id="win"),
        )
        await db.flush()

        dedupe = ChessGameDedupeService(db)
        # Simulate SELECT miss then INSERT race against existing fingerprint.
        with patch.object(dedupe.repo, "get_by_fingerprint", side_effect=[None, winner]):
            from sqlalchemy.exc import IntegrityError

            async def _boom(*_a, **_k):
                raise IntegrityError("stmt", {}, Exception("unique"))

            with patch.object(dedupe.repo, "add", side_effect=_boom):
                outcome = await dedupe.upsert_game(
                    game=chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed),
                    source=SourceRef(provider="lichess_masters", external_id="race"),
                )
        assert outcome.created_game is False
        assert outcome.game.id == winner.id
        assert outcome.created_source is True

    asyncio.run(_run())


def test_analysis_fingerprint_reuse_vs_settings_change() -> None:
    game_fp = "g" * 64
    cfg = normalize_analysis_settings(
        {"depth": 12, "hash_mb": 64, "threads": 1, "time_limit_seconds": None}
    )
    a = compute_analysis_fingerprint(
        game_fingerprint=game_fp, engine_version="16", analysis_settings=cfg
    )
    b = compute_analysis_fingerprint(
        game_fingerprint=game_fp, engine_version="16", analysis_settings=cfg
    )
    c = compute_analysis_fingerprint(
        game_fingerprint=game_fp,
        engine_version="16",
        analysis_settings={**cfg, "depth": 18},
    )
    assert a == b
    assert a != c

"""§7 — famous = local editorial curation; never scheduled PGN redownload."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import cast

from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence import catalog_job_models as job_models
from backend.modules.chess_intelligence import models as chess_models
from backend.modules.chess_intelligence.famous_catalog import (
    FamousGameEntry,
    apply_famous_metadata,
)
from backend.modules.chess_intelligence.famous_policy import (
    FORBIDDEN_FAMOUS_ORM_NAMES,
    famous_curation_is_metadata_only,
    scan_famous_modules_for_provider_calls,
)
from backend.modules.chess_intelligence.historical_assets import (
    FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS,
    forbidden_historical_schedule_hits,
)
from backend.modules.chess_intelligence.models import ChessGame
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant
from backend.workers.celery_app import celery_app

_PGN = """
[Event "Paris"]
[White "Morphy"]
[Black "Allies"]
[Result "1-0"]
[Date "1858.01.01"]

1. e4 e5 2. Nf3 1-0
"""

MODULE_ROOT = Path(__file__).resolve().parents[1] / "modules" / "chess_intelligence"


def test_no_famous_game_orm_table() -> None:
    names = {
        name
        for name in dir(chess_models) + dir(job_models)
        if name[:1].isupper()
    }
    assert FORBIDDEN_FAMOUS_ORM_NAMES.isdisjoint(names)
    assert "chess_famous_games" not in Base.metadata.tables
    assert famous_curation_is_metadata_only() is True


def test_famous_modules_do_not_call_providers() -> None:
    hits = scan_famous_modules_for_provider_calls(MODULE_ROOT)
    assert hits == [], f"famous curation must stay local: {hits}"


def test_beat_does_not_schedule_famous_pgn_redownload() -> None:
    assert "redownload_famous" in FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS
    assert "famous_pgn" in FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS
    hits = forbidden_historical_schedule_hits(dict(celery_app.conf.beat_schedule or {}))
    assert hits == []


def test_apply_famous_metadata_preserves_pgn_and_fingerprint() -> None:
    async def _run() -> None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine.sync_engine, "connect")
        def _fk(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn,
                    tables=cast(list[Table], [Tenant.__table__, ChessGame.__table__]),
                )
            )
        db = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        game = chess_game_from_parsed(
            tenant_id=tenant_id,
            parsed=parse_chess_input(_PGN, "pgn"),
            source_provider="pgn_archive",
        )
        db.add(game)
        await db.flush()
        fingerprint = game.game_fingerprint
        pgn = game.normalized_pgn
        content_hash = game.content_hash

        entry = FamousGameEntry(
            id="demo",
            title="Demo Immortal",
            white="Morphy",
            black="Allies",
            year=1858,
            tags=["immortal"],
            historical_significance="editorial note only",
        )
        assert apply_famous_metadata(game, entry) is True
        assert game.is_famous is True
        assert game.famous_title == "Demo Immortal"
        assert game.game_fingerprint == fingerprint
        assert game.normalized_pgn == pgn
        assert game.content_hash == content_hash
        await db.close()

    asyncio.run(_run())

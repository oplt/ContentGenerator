"""§18 — operational catalog is not a universal chess warehouse."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import cast

from sqlalchemy import Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.importers import (
    PgnArchiveImportConfig,
    PgnArchiveImporter,
)
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource
from backend.modules.chess_intelligence.operational_catalog import (
    DEFAULT_CONTENT_OPPORTUNITY_THRESHOLD,
    OPERATIONAL_CATALOG_PURPOSES,
    SelectiveImportFilters,
    clamp_pgn_import_max_games,
    clamp_provider_sync_max_games,
    filters_from_params,
    game_passes_selective_filters,
)
from backend.modules.identity_access.models import Tenant

_GAME_A = """
[Event "World Championship"]
[White "Kasparov"]
[Black "Karpov"]
[Result "1-0"]
[Date "1990.01.01"]

1. e4 e5 2. Nf3 1-0
"""

_GAME_B = """
[Event "Club Match"]
[White "Alice"]
[Black "Bob"]
[Result "0-1"]
[Date "2010.06.01"]

1. d4 d5 2. c4 0-1
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
                    [Tenant.__table__, ChessGame.__table__, ChessGameSource.__table__],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_operational_purposes_are_content_ops_not_warehouse() -> None:
    assert "historical_famous" in OPERATIONAL_CATALOG_PURPOSES
    assert "video_generation" in OPERATIONAL_CATALOG_PURPOSES
    assert "download_every_game" not in OPERATIONAL_CATALOG_PURPOSES
    assert DEFAULT_CONTENT_OPPORTUNITY_THRESHOLD >= 40


def test_selective_filters_year_and_player() -> None:
    filters = SelectiveImportFilters(year_from=1980, year_to=2000, player="kasparov")
    assert game_passes_selective_filters(
        white_player="Kasparov, G.",
        black_player="Karpov",
        event="WCh",
        game_date="1990.01.01",
        year=1990,
        white_rating=2800,
        black_rating=2700,
        source_provider="pgn_archive",
        filters=filters,
    )
    assert not game_passes_selective_filters(
        white_player="Alice",
        black_player="Bob",
        event="Club",
        game_date="2010.01.01",
        year=2010,
        white_rating=None,
        black_rating=None,
        source_provider="pgn_archive",
        filters=filters,
    )


def test_filters_from_params_and_caps() -> None:
    f = filters_from_params(
        {
            "year_from": "1990",
            "event": "Championship",
            "providers": "pgn_archive,pgn_mentor",
        }
    )
    assert f.year_from == 1990
    assert f.event == "Championship"
    assert f.providers == frozenset({"pgn_archive", "pgn_mentor"})
    assert clamp_pgn_import_max_games(999_999) <= 500_000
    assert clamp_provider_sync_max_games(999) <= 200
    assert clamp_provider_sync_max_games(None) >= 1


def test_importer_applies_selective_filters() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        path = Path("/tmp") / f"chess_op_{tenant_id.hex}.pgn"
        path.write_text(_GAME_A + "\n\n" + _GAME_B, encoding="utf-8")
        try:
            progress = await PgnArchiveImporter(db).run(
                PgnArchiveImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    max_games=10,
                    filters=SelectiveImportFilters(year_to=2000, player="kasparov"),
                )
            )
            assert progress.scanned == 2
            assert progress.skipped_filtered == 1
            assert progress.inserted == 1
            games = (
                (await db.execute(select(ChessGame).where(ChessGame.tenant_id == tenant_id)))
                .scalars()
                .all()
            )
            assert len(games) == 1
            assert games[0].white_player and "Kasparov" in games[0].white_player
        finally:
            path.unlink(missing_ok=True)
            await db.close()

    asyncio.run(_run())


def test_max_games_cap_limits_scan() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        path = Path("/tmp") / f"chess_cap_{tenant_id.hex}.pgn"
        path.write_text(_GAME_A + "\n\n" + _GAME_B, encoding="utf-8")
        try:
            progress = await PgnArchiveImporter(db).run(
                PgnArchiveImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    max_games=1,
                )
            )
            assert progress.scanned == 1
            assert progress.inserted == 1
        finally:
            path.unlink(missing_ok=True)
            await db.close()

    asyncio.run(_run())

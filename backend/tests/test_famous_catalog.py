"""Phase 6 — famous game catalog matching."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast

from sqlalchemy import Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.famous_catalog import (
    apply_famous_metadata,
    best_famous_match,
    load_famous_catalog,
    score_famous_match,
)
from backend.modules.chess_intelligence.famous_service import FamousCatalogService
from backend.modules.chess_intelligence.models import ChessGame
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

# Distinctive Opera Game opening (public domain moves).
_OPERA_PGN = """
[Event "Paris"]
[Site "Paris"]
[Date "1858.??.??"]
[White "Morphy, Paul"]
[Black "Duke of Brunswick / Count Isouard"]
[Result "1-0"]

1. e4 e5 2. Nf3 d6 3. d4 Bg4 4. dxe5 Bxf3 5. Qxf3 dxe5 6. Bc4 Nf6 7. Qb3 Qe7
8. Nc3 c6 9. Bg5 b5 10. Nxb5 cxb5 11. Bxb5+ Nbd7 12. O-O-O Rd8 13. Rxd7 Rxd7
14. Rd1 Qe6 15. Bxd7+ Nxd7 16. Qb8+ Nxb8 17. Rd8# 1-0
"""

_RANDOM_PGN = """
[Event "Club"]
[White "Alice"]
[Black "Bob"]
[Date "2000.01.01"]
[Result "*"]

1. e4 e5 2. Nf3 Nc6
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
                tables=cast(list[Table], [Tenant.__table__, ChessGame.__table__]),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_load_default_catalog() -> None:
    catalog = load_famous_catalog()
    ids = {e.id for e in catalog}
    assert "immortal_game" in ids
    assert "opera_game" in ids
    assert "game_of_the_century" in ids
    assert len(catalog) >= 6


def test_match_opera_game_by_year_players_uci() -> None:
    parsed = parse_chess_input(_OPERA_PGN, "pgn")
    game = chess_game_from_parsed(tenant_id=uuid.uuid4(), parsed=parsed)
    match = best_famous_match(game)
    assert match is not None
    assert match.entry.id == "opera_game"
    assert match.score >= 70
    assert "year" in match.reasons
    assert "uci_prefix" in match.reasons or ("white" in match.reasons and "black" in match.reasons)


def test_reject_name_only_without_year() -> None:
    catalog = load_famous_catalog()
    immortal = next(e for e in catalog if e.id == "immortal_game")
    parsed = parse_chess_input(_RANDOM_PGN, "pgn")
    game = chess_game_from_parsed(tenant_id=uuid.uuid4(), parsed=parsed)
    game.white_player = "Adolf Anderssen"
    game.black_player = "Lionel Kieseritzky"
    game.year = None
    assert score_famous_match(immortal, game) is None


def test_apply_metadata_sets_famous_fields() -> None:
    catalog = load_famous_catalog()
    opera = next(e for e in catalog if e.id == "opera_game")
    parsed = parse_chess_input(_OPERA_PGN, "pgn")
    game = chess_game_from_parsed(tenant_id=uuid.uuid4(), parsed=parsed)
    assert apply_famous_metadata(game, opera) is True
    assert game.is_famous is True
    assert game.famous_title == "The Opera Game"
    assert "famous" in game.historical_tags
    assert "catalog:opera_game" in game.historical_tags
    assert game.source_metadata.get("famous_catalog_id") == "opera_game"


def test_service_apply_to_tenant() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()

        parsed = parse_chess_input(_OPERA_PGN, "pgn")
        game = chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed)
        db.add(game)
        await db.commit()

        report = await FamousCatalogService(db).apply_to_tenant(tenant_id=tenant_id)
        assert report.matched == 1
        assert report.updated == 1

        refreshed = (
            await db.execute(select(ChessGame).where(ChessGame.id == game.id))
        ).scalar_one()
        assert refreshed.is_famous is True
        assert refreshed.famous_title == "The Opera Game"
        await db.close()

    asyncio.run(_run())

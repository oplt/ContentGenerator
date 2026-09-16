"""§22 — ChessVideo stays downstream; no provider ingestion inside chess_video/."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast
from unittest.mock import patch

from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.chess_video.boundary import (
    ALLOWED_CATALOG_IMPORT_FRAGMENTS,
    CORRECT_FLOW,
    MANUAL_INPUT_FORMATS,
    scan_video_provider_leaks,
    video_resolves_from_local_catalog_only,
)
from backend.modules.chess_video.create import resolve_create_payload
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.chess_video.schemas import ChessVideoCreateRequest
from backend.modules.identity_access.models import Tenant

_PGN = """
[Event "Boundary"]
[White "W"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
"""


def test_video_package_has_no_provider_ingestion() -> None:
    assert scan_video_provider_leaks() == []


def test_boundary_documents_downstream_flow() -> None:
    assert CORRECT_FLOW[0] == "Chess Intelligence"
    assert CORRECT_FLOW[-1] == "existing ChessVideo pipeline"
    assert "pgn" in MANUAL_INPUT_FORMATS
    assert "san" in MANUAL_INPUT_FORMATS
    assert "uci" in MANUAL_INPUT_FORMATS
    assert "chess_intelligence.catalog_queries" in ALLOWED_CATALOG_IMPORT_FRAGMENTS
    assert video_resolves_from_local_catalog_only() is True


def test_manual_pgn_san_uci_still_parse() -> None:
    pgn = parse_chess_input(_PGN, "pgn")
    assert pgn.move_count >= 1
    san = parse_chess_input("1. e4 e5 2. Nf3", "san")
    assert san.move_count >= 2
    uci = parse_chess_input("e2e4 e7e5 g1f3", "uci")
    assert uci.move_count >= 2


def test_catalog_resolve_never_calls_providers() -> None:
    async def _run() -> None:
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
                        ],
                    ),
                )
            )
        db = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.flush()
        parsed = parse_chess_input(_PGN, "pgn")
        game = chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed)
        outcome = await ChessGameDedupeService(db).upsert_game(
            game=game,
            source=SourceRef(provider="pgn_archive", external_id="v1"),
        )
        await db.commit()

        with (
            patch(
                "backend.modules.chess_intelligence.providers.registry.get_historical_game_provider"
            ) as hist,
            patch(
                "backend.modules.chess_intelligence.providers.registry.get_puzzle_provider"
            ) as puzzles,
        ):
            resolved, _ = await resolve_create_payload(
                db,
                tenant_id=tenant_id,
                payload=ChessVideoCreateRequest(chess_game_id=outcome.game.id),
            )
        hist.assert_not_called()
        puzzles.assert_not_called()
        assert resolved.source_text == outcome.game.normalized_pgn
        assert resolved.input_format == "pgn"

    asyncio.run(_run())

"""Phase 11 — ChessGame → ChessVideoService bridge (no second renderer)."""

from __future__ import annotations

import asyncio
import uuid
from typing import cast
from unittest.mock import MagicMock

from sqlalchemy import Table, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.chess_video.create import resolve_create_payload
from backend.modules.chess_video.models import ChessVideoJob, ChessVideoJobStatus
from backend.modules.chess_video.schemas import ChessVideoCreateRequest
from backend.modules.chess_video.service import ChessVideoService
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

_PGN = """
[Event "Test"]
[White "Alpha"]
[Black "Beta"]
[Date "2000.01.01"]
[Result "1-0"]

1. e4 e5 2. Nf3 1-0
"""


async def _session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        # ChessVideoJob FKs users; keep PRAGMA off so catalog→video bridge tests stay narrow.
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
                        ChessVideoJob.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_resolve_create_payload_from_catalog_game() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        parsed = parse_chess_input(_PGN, "pgn")
        game = chess_game_from_parsed(
            tenant_id=tenant_id, parsed=parsed, source_provider="pgn_archive"
        )
        game.is_famous = True
        game.famous_title = "Immortal"
        outcome = await ChessGameDedupeService(db).upsert_game(
            game=game,
            source=SourceRef(provider="pgn_archive", external_id="g1"),
        )
        await db.commit()

        resolved, is_famous = await resolve_create_payload(
            db,
            tenant_id=tenant_id,
            payload=ChessVideoCreateRequest(chess_game_id=outcome.game.id),
        )
        assert is_famous is True
        assert resolved.source_text == outcome.game.normalized_pgn
        assert resolved.input_format == "pgn"
        assert resolved.title == "Immortal"
        assert "Alpha" in (resolved.subtitle or "")
        assert "Beta" in (resolved.subtitle or "")

    asyncio.run(_run())


def test_create_from_chess_game_id_queues_job() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        parsed = parse_chess_input(_PGN, "pgn")
        game = chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed)
        outcome = await ChessGameDedupeService(db).upsert_game(
            game=game,
            source=SourceRef(provider="manual", external_id="x1"),
        )
        await db.commit()

        svc = ChessVideoService(db)
        svc._enqueue = MagicMock()  # type: ignore[method-assign]
        job = await svc.create(
            tenant_id=tenant_id,
            user_id=None,
            payload=ChessVideoCreateRequest(
                chess_game_id=outcome.game.id,
                render_preset="economy_vertical",
            ),
        )
        await db.commit()
        assert job.status == ChessVideoJobStatus.QUEUED.value
        assert job.normalized_pgn
        assert job.move_count >= 2
        assert job.white_player == "Alpha"
        assert job.chess_game_id == outcome.game.id
        assert job.render_fingerprint

        # Same path as POST /chess-videos with chess_game_id
        again = await svc.create(
            tenant_id=tenant_id,
            user_id=None,
            payload=ChessVideoCreateRequest(chess_game_id=outcome.game.id),
        )
        assert again.render_fingerprint == job.render_fingerprint

    asyncio.run(_run())


def test_create_requires_source_or_game_id() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChessVideoCreateRequest()


def test_router_exposes_game_video_route() -> None:
    from backend.api.router import api_router

    paths = {getattr(r, "path", "") for r in api_router.routes}
    assert "/api/v1/chess/games/{game_id}/video" in paths

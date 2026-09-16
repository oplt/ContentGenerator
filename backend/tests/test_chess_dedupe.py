"""Phase 5 — fingerprint dedupe + multi-source provenance."""

from __future__ import annotations

import asyncio
import io
import uuid
from pathlib import Path
from typing import cast

from sqlalchemy import Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.fingerprint import (
    compute_game_fingerprint,
    fingerprint_from_parsed,
    normalize_player_name,
)
from backend.modules.chess_intelligence.importers import (
    PgnArchiveImportConfig,
    PgnArchiveImporter,
    iter_pgn_games,
)
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.identity_access.models import Tenant

_GAME = """
[Event "A"]
[White "Kasparov, G."]
[Black "Karpov"]
[Result "1-0"]
[Date "1990.01.01"]

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


def test_fingerprint_stable_move_based() -> None:
    a = parse_chess_input("1. e4 e5 2. Nf3", "san")
    b = parse_chess_input("e2e4 e7e5 g1f3", "uci")
    assert fingerprint_from_parsed(a) == fingerprint_from_parsed(b)
    assert compute_game_fingerprint(
        starting_fen=a.starting_fen,
        uci_moves=a.uci_moves,
        result=a.result,
    ) == fingerprint_from_parsed(a)


def test_normalize_player_name() -> None:
    assert normalize_player_name("Kasparov, G.") == "kasparov g"
    assert normalize_player_name(None) == ""


def test_upsert_links_second_provider_same_fingerprint() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()

        parsed = parse_chess_input(_GAME, "pgn")
        game1 = chess_game_from_parsed(
            tenant_id=tenant_id,
            parsed=parsed,
            source_provider="lichess_masters",
        )
        dedupe = ChessGameDedupeService(db)
        first = await dedupe.upsert_game(
            game=game1,
            source=SourceRef(provider="lichess_masters", external_id="abc123"),
        )
        assert first.created_game is True
        assert first.created_source is True

        game2 = chess_game_from_parsed(
            tenant_id=tenant_id,
            parsed=parsed,
            source_provider="pgn_mentor",
        )
        second = await dedupe.upsert_game(
            game=game2,
            source=SourceRef(
                provider="pgn_mentor",
                source_name="wch",
                source_metadata={"game_index": 1},
            ),
        )
        assert second.created_game is False
        assert second.created_source is True
        assert second.game.id == first.game.id

        # Same Lichess id again → no new source
        again = await dedupe.upsert_game(
            game=chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed),
            source=SourceRef(provider="lichess_masters", external_id="abc123"),
        )
        assert again.created_game is False
        assert again.created_source is False

        sources = await dedupe.repo.list_sources_for_game(
            tenant_id=tenant_id, chess_game_id=first.game.id
        )
        assert len(sources) == 2
        providers = {s.provider for s in sources}
        assert providers == {"lichess_masters", "pgn_mentor"}
        await db.commit()
        await db.close()

    asyncio.run(_run())


def test_importer_links_instead_of_duplicating_game() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()

        # Pre-seed via "lichess"
        parsed = parse_chess_input(_GAME, "pgn")
        seed = chess_game_from_parsed(tenant_id=tenant_id, parsed=parsed)
        await ChessGameDedupeService(db).upsert_game(
            game=seed,
            source=SourceRef(provider="lichess_masters", external_id="seed1"),
        )
        await db.commit()

        path = Path("/tmp") / f"chess_p5_{tenant_id.hex}.pgn"
        path.write_text(_GAME, encoding="utf-8")
        try:
            progress = await PgnArchiveImporter(db).run(
                PgnArchiveImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    provider="pgn_mentor",
                    source_name="archive_a",
                )
            )
            assert progress.inserted == 0
            assert progress.linked_source == 1
            games = (
                (await db.execute(select(ChessGame).where(ChessGame.tenant_id == tenant_id)))
                .scalars()
                .all()
            )
            assert len(games) == 1
            sources = (
                (
                    await db.execute(
                        select(ChessGameSource).where(ChessGameSource.chess_game_id == games[0].id)
                    )
                )
                .scalars()
                .all()
            )
            assert len(sources) == 2
        finally:
            path.unlink(missing_ok=True)
            await db.close()

    asyncio.run(_run())


def test_iter_still_streams() -> None:
    assert len(list(iter_pgn_games(io.StringIO(_GAME)))) == 1

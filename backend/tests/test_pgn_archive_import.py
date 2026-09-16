"""Phase 4 — streaming PGN archive import."""

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
from backend.modules.chess_intelligence.importers import (
    PgnArchiveImportConfig,
    PgnArchiveImporter,
    iter_pgn_games,
)
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource
from backend.modules.identity_access.models import Tenant

_GAME_A = """
[Event "A"]
[White "One"]
[Black "Two"]
[Result "1-0"]
[Date "1990.01.01"]

1. e4 e5 2. Nf3 1-0
"""

_GAME_B = """
[Event "B"]
[White "Three"]
[Black "Four"]
[Result "0-1"]
[Date "1991.01.01"]

1. d4 d5 2. c4 0-1
"""

_ARCHIVE = _GAME_A + "\n\n" + _GAME_B + "\n\n" + _GAME_A  # third = duplicate of A


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
                    list[Table], [Tenant.__table__, ChessGame.__table__, ChessGameSource.__table__]
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_iter_pgn_games_streams_multiple() -> None:
    games = list(iter_pgn_games(io.StringIO(_ARCHIVE)))
    assert len(games) == 3
    assert games[0][0] == 1
    assert '[Event "A"]' in games[0][1]
    assert '[Event "B"]' in games[1][1]


def test_import_inserts_and_dedupes() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()

        path = Path("/tmp") / f"chess_import_{tenant_id.hex}.pgn"
        path.write_text(_ARCHIVE, encoding="utf-8")
        try:
            progress = await PgnArchiveImporter(db).run(
                PgnArchiveImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    provider="pgn_mentor",
                    source_name="test_set",
                    batch_size=10,
                )
            )
            assert progress.scanned == 3
            assert progress.inserted == 2
            # Same fingerprint at different archive index → link source, not new game
            assert progress.linked_source == 1
            assert progress.skipped_error == 0
            assert progress.batches_committed >= 1

            rows = (
                (
                    await db.execute(
                        select(ChessGame).where(
                            ChessGame.tenant_id == tenant_id,
                            ChessGame.deleted_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 2
            assert all(r.source_provider == "pgn_mentor" for r in rows)
            assert all(r.source_metadata.get("source_name") == "test_set" for r in rows)

            # Idempotent re-import (same source_name + game_index)
            again = await PgnArchiveImporter(db).run(
                PgnArchiveImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    provider="pgn_mentor",
                    source_name="test_set",
                )
            )
            assert again.inserted == 0
            assert again.skipped_duplicate == 3
        finally:
            path.unlink(missing_ok=True)
            await db.close()

    asyncio.run(_run())


def test_dry_run_does_not_persist() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        path = Path("/tmp") / f"chess_dry_{tenant_id.hex}.pgn"
        path.write_text(_GAME_A, encoding="utf-8")
        try:
            progress = await PgnArchiveImporter(db).run(
                PgnArchiveImportConfig(
                    tenant_id=tenant_id,
                    file_path=path,
                    dry_run=True,
                )
            )
            assert progress.inserted == 1
            assert progress.batches_committed == 0
            count = (
                await db.execute(select(ChessGame.id).where(ChessGame.tenant_id == tenant_id))
            ).all()
            assert count == []
        finally:
            path.unlink(missing_ok=True)
            await db.close()

    asyncio.run(_run())


def test_parse_error_counted_and_continues() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        empty = """
[Event "Empty"]
[White "X"]
[Black "Y"]
[Result "*"]

*
"""
        path = Path("/tmp") / f"chess_bad_{tenant_id.hex}.pgn"
        path.write_text(empty + "\n\n" + _GAME_A, encoding="utf-8")
        try:
            progress = await PgnArchiveImporter(db).run(
                PgnArchiveImportConfig(tenant_id=tenant_id, file_path=path)
            )
            assert progress.skipped_error >= 1
            assert progress.inserted == 1
        finally:
            path.unlink(missing_ok=True)
            await db.close()

    asyncio.run(_run())

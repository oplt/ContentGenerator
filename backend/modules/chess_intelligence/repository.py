"""Persistence for canonical chess catalog entities."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource, ChessPuzzle


class ChessGameRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_fingerprint(
        self,
        *,
        tenant_id: uuid.UUID,
        game_fingerprint: str,
    ) -> ChessGame | None:
        result = await self.db.execute(
            select(ChessGame).where(
                ChessGame.tenant_id == tenant_id,
                ChessGame.game_fingerprint == game_fingerprint,
                ChessGame.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def existing_fingerprints(
        self,
        *,
        tenant_id: uuid.UUID,
        fingerprints: Sequence[str],
    ) -> set[str]:
        if not fingerprints:
            return set()
        result = await self.db.execute(
            select(ChessGame.game_fingerprint).where(
                ChessGame.tenant_id == tenant_id,
                ChessGame.game_fingerprint.in_(list(fingerprints)),
                ChessGame.deleted_at.is_(None),
            )
        )
        return {row[0] for row in result.all()}

    async def map_by_fingerprints(
        self,
        *,
        tenant_id: uuid.UUID,
        fingerprints: Sequence[str],
    ) -> dict[str, ChessGame]:
        if not fingerprints:
            return {}
        result = await self.db.execute(
            select(ChessGame).where(
                ChessGame.tenant_id == tenant_id,
                ChessGame.game_fingerprint.in_(list(fingerprints)),
                ChessGame.deleted_at.is_(None),
            )
        )
        return {g.game_fingerprint: g for g in result.scalars().all()}

    async def add(self, game: ChessGame) -> ChessGame:
        self.db.add(game)
        await self.db.flush()
        return game

    async def get_by_provider_external_id(
        self,
        *,
        tenant_id: uuid.UUID,
        provider: str,
        external_id: str,
    ) -> ChessGame | None:
        """Canonical catalog hit — denormalized primary *or* any ChessGameSource row.

        Secondary providers attach provenance without rewriting ``ChessGame.source_*``;
        lookups must still find the game via ``chess_game_sources``.
        """
        primary = await self.db.execute(
            select(ChessGame).where(
                ChessGame.tenant_id == tenant_id,
                ChessGame.source_provider == provider,
                ChessGame.source_external_id == external_id,
                ChessGame.deleted_at.is_(None),
            )
        )
        hit = primary.scalar_one_or_none()
        if hit is not None:
            return hit

        via_source = await self.db.execute(
            select(ChessGame)
            .join(
                ChessGameSource,
                ChessGameSource.chess_game_id == ChessGame.id,
            )
            .where(
                ChessGame.tenant_id == tenant_id,
                ChessGame.deleted_at.is_(None),
                ChessGameSource.tenant_id == tenant_id,
                ChessGameSource.provider == provider,
                ChessGameSource.external_id == external_id,
            )
            .limit(1)
        )
        return via_source.scalar_one_or_none()

    async def add_many(self, games: Sequence[ChessGame]) -> int:
        if not games:
            return 0
        self.db.add_all(list(games))
        await self.db.flush()
        return len(games)

    async def list_for_tenant(
        self,
        *,
        tenant_id: uuid.UUID,
        limit: int = 5000,
        year: int | None = None,
    ) -> Sequence[ChessGame]:
        stmt = select(ChessGame).where(
            ChessGame.tenant_id == tenant_id,
            ChessGame.deleted_at.is_(None),
        )
        if year is not None:
            stmt = stmt.where(ChessGame.year == year)
        stmt = stmt.order_by(ChessGame.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def add_source(self, source: ChessGameSource) -> ChessGameSource:
        self.db.add(source)
        await self.db.flush()
        return source

    async def list_sources_for_game(
        self,
        *,
        tenant_id: uuid.UUID,
        chess_game_id: uuid.UUID,
    ) -> Sequence[ChessGameSource]:
        result = await self.db.execute(
            select(ChessGameSource)
            .where(
                ChessGameSource.tenant_id == tenant_id,
                ChessGameSource.chess_game_id == chess_game_id,
            )
            .order_by(ChessGameSource.created_at.asc())
        )
        return result.scalars().all()

    async def source_exists(
        self,
        *,
        tenant_id: uuid.UUID,
        chess_game_id: uuid.UUID,
        provider: str,
        external_id: str | None,
        source_name: str | None = None,
        source_metadata: dict[str, Any] | None = None,
        import_batch_id: str | None = None,
    ) -> bool:
        """True if this sighting is already recorded."""
        _ = import_batch_id  # batch retained on row; identity uses source_name+index
        meta = source_metadata or {}
        if external_id:
            found = await self.db.execute(
                select(ChessGameSource.id).where(
                    ChessGameSource.tenant_id == tenant_id,
                    ChessGameSource.provider == provider,
                    ChessGameSource.external_id == external_id,
                )
            )
            return found.scalar_one_or_none() is not None

        game_index = meta.get("game_index")
        rows = await self.db.execute(
            select(ChessGameSource).where(
                ChessGameSource.tenant_id == tenant_id,
                ChessGameSource.chess_game_id == chess_game_id,
                ChessGameSource.provider == provider,
                ChessGameSource.external_id.is_(None),
            )
        )
        for row in rows.scalars().all():
            if source_name is not None and row.source_name != source_name:
                continue
            if game_index is not None and row.source_metadata.get("game_index") != game_index:
                continue
            return True
        return False


class ChessPuzzleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_fingerprint(
        self,
        *,
        tenant_id: uuid.UUID,
        puzzle_fingerprint: str,
    ) -> ChessPuzzle | None:
        result = await self.db.execute(
            select(ChessPuzzle).where(
                ChessPuzzle.tenant_id == tenant_id,
                ChessPuzzle.puzzle_fingerprint == puzzle_fingerprint,
                ChessPuzzle.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def add(self, puzzle: ChessPuzzle) -> ChessPuzzle:
        self.db.add(puzzle)
        await self.db.flush()
        return puzzle

    async def add_many(self, puzzles: Sequence[ChessPuzzle]) -> int:
        if not puzzles:
            return 0
        self.db.add_all(list(puzzles))
        await self.db.flush()
        return len(puzzles)

    async def get_by_provider_external_id(
        self,
        *,
        tenant_id: uuid.UUID,
        provider: str,
        external_id: str,
    ) -> ChessPuzzle | None:
        result = await self.db.execute(
            select(ChessPuzzle).where(
                ChessPuzzle.tenant_id == tenant_id,
                ChessPuzzle.provider == provider,
                ChessPuzzle.external_id == external_id,
                ChessPuzzle.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_daily_for_day(
        self,
        *,
        tenant_id: uuid.UUID,
        day_utc: str,
    ) -> ChessPuzzle | None:
        """Return catalog puzzle marked as the UTC daily for ``day_utc``, if any.

        Filters in Python after a bounded recent fetch so SQLite test DBs and
        PostgreSQL JSON columns behave the same (``.contains`` is dialect-specific).
        """
        result = await self.db.execute(
            select(ChessPuzzle)
            .where(
                ChessPuzzle.tenant_id == tenant_id,
                ChessPuzzle.deleted_at.is_(None),
            )
            .order_by(ChessPuzzle.retrieved_at.desc().nullslast(), ChessPuzzle.created_at.desc())
            .limit(100)
        )
        for puzzle in result.scalars().all():
            meta = puzzle.source_metadata or {}
            if meta.get("daily_utc") == day_utc:
                return puzzle
        return None

    async def get_latest_daily(
        self,
        *,
        tenant_id: uuid.UUID,
    ) -> ChessPuzzle | None:
        """Most recently retrieved puzzle that was marked as a daily (any day)."""
        result = await self.db.execute(
            select(ChessPuzzle)
            .where(
                ChessPuzzle.tenant_id == tenant_id,
                ChessPuzzle.deleted_at.is_(None),
            )
            .order_by(ChessPuzzle.retrieved_at.desc().nullslast(), ChessPuzzle.created_at.desc())
            .limit(100)
        )
        for puzzle in result.scalars().all():
            meta = puzzle.source_metadata or {}
            if meta.get("daily_utc"):
                return puzzle
        return None

    async def existing_external_ids(
        self,
        *,
        tenant_id: uuid.UUID,
        provider: str,
        external_ids: Sequence[str],
    ) -> set[str]:
        if not external_ids:
            return set()
        result = await self.db.execute(
            select(ChessPuzzle.external_id).where(
                ChessPuzzle.tenant_id == tenant_id,
                ChessPuzzle.provider == provider,
                ChessPuzzle.external_id.in_(list(external_ids)),
                ChessPuzzle.deleted_at.is_(None),
            )
        )
        return {row[0] for row in result.all()}

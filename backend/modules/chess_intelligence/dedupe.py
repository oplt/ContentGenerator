"""Upsert canonical ChessGame + attach ChessGameSource provenance."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource
from backend.modules.chess_intelligence.repository import ChessGameRepository


@dataclass
class SourceRef:
    provider: str
    external_id: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)
    import_batch_id: str | None = None
    license_note: str | None = None
    retrieved_at: datetime | None = None


@dataclass
class PersistOutcome:
    game: ChessGame
    created_game: bool
    created_source: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChessGameDedupeService:
    """One fingerprint → one ChessGame; many SourceRef rows."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ChessGameRepository(db)

    async def upsert_game(
        self,
        *,
        game: ChessGame,
        source: SourceRef,
    ) -> PersistOutcome:
        """Insert game if new fingerprint; always try to attach source provenance."""
        existing = await self.repo.get_by_fingerprint(
            tenant_id=game.tenant_id,
            game_fingerprint=game.game_fingerprint,
        )
        created_game = False
        if existing is None:
            # Denormalized primary source fields on the game row.
            game.source_provider = source.provider
            game.source_external_id = source.external_id
            game.source_url = source.source_url
            game.source_metadata = dict(source.source_metadata)
            await self.repo.add(game)
            created_game = True
            target = game
        else:
            target = existing
            _enrich_sparse_fields(target, game)

        created_source = await self._attach_source(
            game=target,
            source=source,
            is_primary=created_game,
        )
        return PersistOutcome(
            game=target,
            created_game=created_game,
            created_source=created_source,
        )

    async def _attach_source(
        self,
        *,
        game: ChessGame,
        source: SourceRef,
        is_primary: bool,
    ) -> bool:
        if await self.repo.source_exists(
            tenant_id=game.tenant_id,
            chess_game_id=game.id,
            provider=source.provider,
            external_id=source.external_id,
            source_name=source.source_name,
            source_metadata=source.source_metadata,
            import_batch_id=source.import_batch_id,
        ):
            return False

        row = ChessGameSource(
            id=uuid.uuid4(),
            tenant_id=game.tenant_id,
            chess_game_id=game.id,
            provider=source.provider,
            external_id=source.external_id,
            source_url=source.source_url,
            source_name=source.source_name,
            source_metadata=dict(source.source_metadata),
            import_batch_id=source.import_batch_id,
            license_note=source.license_note,
            retrieved_at=source.retrieved_at or _utcnow(),
            is_primary=is_primary,
        )
        await self.repo.add_source(row)
        return True


def _enrich_sparse_fields(target: ChessGame, incoming: ChessGame) -> None:
    """Fill blank catalog fields from a later sighting without overwriting."""
    for field_name in (
        "white_player",
        "black_player",
        "white_rating",
        "black_rating",
        "event",
        "site",
        "round",
        "game_date",
        "year",
        "result",
        "eco",
        "opening",
        "variation",
        "final_fen",
    ):
        if getattr(target, field_name) is None and getattr(incoming, field_name) is not None:
            setattr(target, field_name, getattr(incoming, field_name))

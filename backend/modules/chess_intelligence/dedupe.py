"""Upsert canonical ChessGame + attach ChessGameSource provenance.

§16 — one fingerprint → one ChessGame; later providers add ChessGameSource rows
and must never overwrite earlier ``source_*`` / provenance associations.

§17 — sole game-dedupe entrypoint. Do not add provider-local or path-local
dedupe; all ingress uses ``fingerprint`` + ``ChessGameDedupeService``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.historical_assets import IMMUTABLE_GAME_FIELDS
from backend.modules.chess_intelligence.licenses import license_for_provider
from backend.modules.chess_intelligence.models import ChessGame, ChessGameSource
from backend.modules.chess_intelligence.repository import ChessGameRepository


@dataclass
class SourceRef:
    """One provider sighting (provider, external id, URL, name, retrieved_at, license, meta)."""

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
        """Insert game if new fingerprint; always try to attach source provenance.

        §28 — concurrent same-fingerprint inserts: SAVEPOINT + IntegrityError →
        re-load winner (DB unique on ``game_fingerprint`` is source of truth).
        """
        existing = await self.repo.get_by_fingerprint(
            tenant_id=game.tenant_id,
            game_fingerprint=game.game_fingerprint,
        )
        created_game = False
        if existing is None:
            # Denormalized primary source fields — set once on create only.
            game.source_provider = source.provider
            game.source_external_id = source.external_id
            game.source_url = source.source_url
            game.source_metadata = dict(source.source_metadata)
            try:
                async with self.db.begin_nested():
                    await self.repo.add(game)
                created_game = True
                target = game
            except IntegrityError:
                # Peer won the fingerprint race — attach source to their row.
                raced = await self.repo.get_by_fingerprint(
                    tenant_id=game.tenant_id,
                    game_fingerprint=game.game_fingerprint,
                )
                if raced is None:
                    raise
                target = raced
                _enrich_sparse_fields(target, game)
        else:
            target = existing
            # Never rewrite primary provenance or immutable PGN/fingerprint fields.
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
            license_note=source.license_note or license_for_provider(source.provider),
            retrieved_at=source.retrieved_at or _utcnow(),
            is_primary=is_primary,
        )
        try:
            async with self.db.begin_nested():
                await self.repo.add_source(row)
        except IntegrityError:
            # Concurrent same provider+external_id — unique index is SoT.
            return False
        return True


def _enrich_sparse_fields(target: ChessGame, incoming: ChessGame) -> None:
    """Fill blank catalog fields from a later sighting without overwriting.

    Never mutates ``IMMUTABLE_GAME_FIELDS`` (durable local asset contract).
    """
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
    ):
        if field_name in IMMUTABLE_GAME_FIELDS:
            continue
        if getattr(target, field_name) is None and getattr(incoming, field_name) is not None:
            setattr(target, field_name, getattr(incoming, field_name))
    # final_fen is immutable once set; only fill if blank (rare incomplete import).
    if target.final_fen is None and incoming.final_fen is not None:
        target.final_fen = incoming.final_fen

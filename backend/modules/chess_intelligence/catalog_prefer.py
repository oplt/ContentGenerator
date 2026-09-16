"""Prefer canonical catalog rows over provider refetch (Phase 22)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.models import ChessGame, ChessPuzzle
from backend.modules.chess_intelligence.providers.base import HistoricalGameProvider
from backend.modules.chess_intelligence.providers.dtos import ExternalChessGame
from backend.modules.chess_intelligence.repository import (
    ChessGameRepository,
    ChessPuzzleRepository,
)


async def catalog_game_if_present(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    provider: str,
    external_id: str,
) -> ChessGame | None:
    return await ChessGameRepository(db).get_by_provider_external_id(
        tenant_id=tenant_id,
        provider=provider,
        external_id=external_id,
    )


async def catalog_puzzle_if_present(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    provider: str,
    external_id: str,
) -> ChessPuzzle | None:
    return await ChessPuzzleRepository(db).get_by_provider_external_id(
        tenant_id=tenant_id,
        provider=provider,
        external_id=external_id,
    )


async def get_external_game_prefer_catalog(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    provider: HistoricalGameProvider,
    external_id: str,
) -> ExternalChessGame | ChessGame:
    """Return catalog row when persisted; otherwise provider get_game (Redis-cached)."""
    existing = await catalog_game_if_present(
        db,
        tenant_id=tenant_id,
        provider=provider.name,
        external_id=external_id,
    )
    if existing is not None:
        return existing
    return await provider.get_game(external_id)

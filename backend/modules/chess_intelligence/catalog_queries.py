"""Filtered catalog queries for chess games / puzzles (cursor pagination)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from backend.modules.chess_intelligence.models import ChessGame, ChessPuzzle
from backend.modules.shared.pagination import decode_cursor, encode_cursor


@dataclass(frozen=True)
class GameSearchFilters:
    player: str | None = None
    white: str | None = None
    black: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    event: str | None = None
    result: str | None = None
    opening: str | None = None
    eco: str | None = None
    famous_only: bool = False
    provider: str | None = None
    min_rating: int | None = None
    max_rating: int | None = None
    tag: str | None = None


@dataclass(frozen=True)
class PuzzleSearchFilters:
    min_rating: int | None = None
    max_rating: int | None = None
    theme: str | None = None
    opening: str | None = None
    min_popularity: int | None = None
    provider: str | None = None


@dataclass
class PageResult:
    items: list[Any]
    next_cursor: str | None
    has_more: bool


def _like(value: str) -> str:
    return f"%{value.lower()}%"


def _id_sort_key(model: type[ChessGame] | type[ChessPuzzle]) -> ColumnElement[str]:
    # SQLite Uuid casts to hex-without-hyphens; Postgres text may include hyphens.
    return func.replace(cast(model.id, String), "-", "")


def _created_second_key(model: type[ChessGame] | type[ChessPuzzle]) -> ColumnElement[str]:
    # Avoid SQLite binding ``…20.000000`` vs stored ``…20`` false ``<`` matches.
    return func.substr(cast(model.created_at, String), 1, 19)


def _cursor_clause(
    model: type[ChessGame] | type[ChessPuzzle],
    created_at: datetime,
    entity_id: uuid.UUID,
) -> ColumnElement[bool]:
    ca = created_at.replace(microsecond=0)
    if ca.tzinfo is not None:
        ca = ca.replace(tzinfo=None)
    ca_str = ca.strftime("%Y-%m-%d %H:%M:%S")
    created_key = _created_second_key(model)
    id_key = _id_sort_key(model)
    return or_(
        created_key < ca_str,
        and_(created_key == ca_str, id_key < entity_id.hex),
    )


class ChessCatalogQuery:
    """Tenant-scoped search with stable (created_at DESC, id DESC) ordering."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_game(
        self, *, tenant_id: uuid.UUID, game_id: uuid.UUID
    ) -> ChessGame | None:
        result = await self.db.execute(
            select(ChessGame).where(
                ChessGame.tenant_id == tenant_id,
                ChessGame.id == game_id,
                ChessGame.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_puzzle(
        self, *, tenant_id: uuid.UUID, puzzle_id: uuid.UUID
    ) -> ChessPuzzle | None:
        result = await self.db.execute(
            select(ChessPuzzle).where(
                ChessPuzzle.tenant_id == tenant_id,
                ChessPuzzle.id == puzzle_id,
                ChessPuzzle.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def search_games(
        self,
        *,
        tenant_id: uuid.UUID,
        filters: GameSearchFilters,
        limit: int = 50,
        cursor: str | None = None,
    ) -> PageResult:
        limit = min(max(limit, 1), 100)
        stmt = select(ChessGame).where(
            ChessGame.tenant_id == tenant_id,
            ChessGame.deleted_at.is_(None),
        )
        stmt = self._apply_game_filters(stmt, filters)
        decoded = None
        if cursor:
            try:
                decoded = decode_cursor(cursor)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Invalid cursor") from exc
        if decoded is not None:
            created_at, entity_id = decoded
            stmt = stmt.where(_cursor_clause(ChessGame, created_at, entity_id))
        stmt = stmt.order_by(
            ChessGame.created_at.desc(), _id_sort_key(ChessGame).desc()
        ).limit(limit + 1)
        rows = list((await self.db.execute(stmt)).scalars().all())
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            stamp = last.created_at.replace(microsecond=0)
            if stamp.tzinfo is not None:
                stamp = stamp.replace(tzinfo=None)
            next_cursor = encode_cursor(stamp, last.id)
        return PageResult(items=items, next_cursor=next_cursor, has_more=has_more)

    async def search_puzzles(
        self,
        *,
        tenant_id: uuid.UUID,
        filters: PuzzleSearchFilters,
        limit: int = 50,
        cursor: str | None = None,
    ) -> PageResult:
        limit = min(max(limit, 1), 100)
        stmt = select(ChessPuzzle).where(
            ChessPuzzle.tenant_id == tenant_id,
            ChessPuzzle.deleted_at.is_(None),
        )
        stmt = self._apply_puzzle_filters(stmt, filters)
        decoded = None
        if cursor:
            try:
                decoded = decode_cursor(cursor)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Invalid cursor") from exc
        if decoded is not None:
            created_at, entity_id = decoded
            stmt = stmt.where(_cursor_clause(ChessPuzzle, created_at, entity_id))
        stmt = stmt.order_by(
            ChessPuzzle.created_at.desc(), _id_sort_key(ChessPuzzle).desc()
        ).limit(limit + 1)
        rows = list((await self.db.execute(stmt)).scalars().all())
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            stamp = last.created_at.replace(microsecond=0)
            if stamp.tzinfo is not None:
                stamp = stamp.replace(tzinfo=None)
            next_cursor = encode_cursor(stamp, last.id)
        return PageResult(items=items, next_cursor=next_cursor, has_more=has_more)

    def _apply_game_filters(self, stmt: Any, f: GameSearchFilters) -> Any:
        if f.player:
            needle = _like(f.player)
            stmt = stmt.where(
                or_(
                    func.lower(ChessGame.white_player).like(needle),
                    func.lower(ChessGame.black_player).like(needle),
                )
            )
        if f.white:
            stmt = stmt.where(func.lower(ChessGame.white_player).like(_like(f.white)))
        if f.black:
            stmt = stmt.where(func.lower(ChessGame.black_player).like(_like(f.black)))
        if f.year_from is not None:
            stmt = stmt.where(ChessGame.year >= f.year_from)
        if f.year_to is not None:
            stmt = stmt.where(ChessGame.year <= f.year_to)
        if f.event:
            stmt = stmt.where(func.lower(ChessGame.event).like(_like(f.event)))
        if f.result:
            stmt = stmt.where(ChessGame.result == f.result)
        if f.opening:
            stmt = stmt.where(func.lower(ChessGame.opening).like(_like(f.opening)))
        if f.eco:
            stmt = stmt.where(func.lower(ChessGame.eco) == f.eco.lower())
        if f.famous_only:
            stmt = stmt.where(ChessGame.is_famous.is_(True))
        if f.provider:
            stmt = stmt.where(ChessGame.source_provider == f.provider)
        if f.min_rating is not None:
            stmt = stmt.where(
                or_(
                    ChessGame.white_rating >= f.min_rating,
                    ChessGame.black_rating >= f.min_rating,
                )
            )
        if f.max_rating is not None:
            stmt = stmt.where(
                or_(
                    ChessGame.white_rating <= f.max_rating,
                    ChessGame.black_rating <= f.max_rating,
                )
            )
        if f.tag:
            # JSON array contains (Postgres + SQLite JSON)
            stmt = stmt.where(ChessGame.historical_tags.contains([f.tag]))
        return stmt

    def _apply_puzzle_filters(self, stmt: Any, f: PuzzleSearchFilters) -> Any:
        if f.min_rating is not None:
            stmt = stmt.where(ChessPuzzle.rating >= f.min_rating)
        if f.max_rating is not None:
            stmt = stmt.where(ChessPuzzle.rating <= f.max_rating)
        if f.min_popularity is not None:
            stmt = stmt.where(ChessPuzzle.popularity >= f.min_popularity)
        if f.provider:
            stmt = stmt.where(ChessPuzzle.provider == f.provider)
        if f.theme:
            stmt = stmt.where(ChessPuzzle.themes.contains([f.theme]))
        if f.opening:
            stmt = stmt.where(ChessPuzzle.opening_tags.contains([f.opening]))
        return stmt

"""Chess catalog search / import / daily puzzle application service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.catalog_concepts import classify_orm_game
from backend.modules.chess_intelligence.catalog_queries import (
    ChessCatalogQuery,
    GameSearchFilters,
    PuzzleSearchFilters,
)
from backend.modules.chess_intelligence.daily_freshness import (
    daily_puzzle_response,
    utc_day,
)
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.ingestion_mode import (
    ChessIngestionMode,
    stamp_ingestion_mode,
)
from backend.modules.chess_intelligence.licenses import license_for_provider
from backend.modules.chess_intelligence.models import ChessGame, ChessPuzzle
from backend.modules.chess_intelligence.moves import annotate_moves
from backend.modules.chess_intelligence.normalizer import (
    chess_game_from_parsed,
    normalize_external_puzzle,
)
from backend.modules.chess_intelligence.providers.http_errors import (
    http_exception_for_chess_failure,
)
from backend.modules.chess_intelligence.providers.registry import get_puzzle_provider
from backend.modules.chess_intelligence.repository import ChessPuzzleRepository
from backend.modules.chess_intelligence.schemas import (
    AnnotatedChessMoveSchema,
    ChessDailyPuzzleResponse,
    ChessGameImportRequest,
    ChessGameImportResponse,
    ChessGamePageResponse,
    ChessGameResponse,
    ChessPuzzlePageResponse,
    ChessPuzzleResponse,
)
from backend.modules.chess_intelligence.source_rules import (
    ChessSourceRuleError,
    assert_provider_allowed_for_ingest,
    assert_url_not_scrape_target,
)
from backend.modules.chess_video.parser import ChessParseError, parse_chess_input


def _game_response(game: ChessGame) -> ChessGameResponse:
    """Serialize catalog game with derived recent/notable flags (§8)."""
    flags = classify_orm_game(game)
    base = ChessGameResponse.model_validate(game)
    return base.model_copy(
        update={"is_recent": flags.is_recent, "is_notable": flags.is_notable}
    )


class ChessCatalogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.queries = ChessCatalogQuery(db)
        self.dedupe = ChessGameDedupeService(db)
        self.puzzles = ChessPuzzleRepository(db)

    async def list_games(
        self,
        *,
        tenant_id: uuid.UUID,
        filters: GameSearchFilters,
        limit: int,
        cursor: str | None,
    ) -> ChessGamePageResponse:
        try:
            page = await self.queries.search_games(
                tenant_id=tenant_id, filters=filters, limit=limit, cursor=cursor
            )
        except Exception as exc:  # noqa: BLE001 — invalid cursor / decode
            if "cursor" in str(exc).lower() or isinstance(exc, (ValueError, IndexError)):
                raise HTTPException(status_code=422, detail="Invalid cursor") from exc
            raise
        return ChessGamePageResponse(
            items=[_game_response(g) for g in page.items],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )

    async def get_game(self, *, tenant_id: uuid.UUID, game_id: uuid.UUID) -> ChessGameResponse:
        game = await self.queries.get_game(tenant_id=tenant_id, game_id=game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")
        return _game_response(game)

    async def get_game_moves(
        self, *, tenant_id: uuid.UUID, game_id: uuid.UUID
    ) -> list[AnnotatedChessMoveSchema]:
        game = await self.queries.get_game(tenant_id=tenant_id, game_id=game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")
        try:
            parsed = parse_chess_input(game.normalized_pgn, "pgn")
        except ChessParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return [
            AnnotatedChessMoveSchema(
                ply=m.ply,
                move_number=m.move_number,
                side=m.side,
                san=m.san,
                uci=m.uci,
                fen_before=m.fen_before,
                fen_after=m.fen_after,
            )
            for m in annotate_moves(parsed)
        ]

    async def import_game(
        self, *, tenant_id: uuid.UUID, payload: ChessGameImportRequest
    ) -> ChessGameImportResponse:
        try:
            provider = assert_provider_allowed_for_ingest(payload.provider)
            # Citation URLs OK; automated scrape targets rejected when provider implies fetch.
            assert_url_not_scrape_target(
                payload.source_url,
                for_automated_fetch=provider not in {"manual", "api_import", "famous_catalog"},
            )
        except ChessSourceRuleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            parsed = parse_chess_input(payload.pgn, "pgn")
        except ChessParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        game = chess_game_from_parsed(
            tenant_id=tenant_id,
            parsed=parsed,
            source_provider=provider,
            source_external_id=payload.external_id,
            source_url=payload.source_url,
        )
        outcome = await self.dedupe.upsert_game(
            game=game,
            source=SourceRef(
                provider=provider,
                external_id=payload.external_id,
                source_url=payload.source_url,
                source_name=payload.source_name or "api_import",
                source_metadata=stamp_ingestion_mode(
                    {"via": "chess_search_api"},
                    ChessIngestionMode.MANUAL_IMPORT,
                ),
                license_note=license_for_provider(provider) or license_for_provider("api_import"),
                retrieved_at=datetime.now(timezone.utc),
            ),
        )
        return ChessGameImportResponse(
            game=_game_response(outcome.game),
            created_game=outcome.created_game,
            created_source=outcome.created_source,
        )

    async def list_puzzles(
        self,
        *,
        tenant_id: uuid.UUID,
        filters: PuzzleSearchFilters,
        limit: int,
        cursor: str | None,
    ) -> ChessPuzzlePageResponse:
        try:
            page = await self.queries.search_puzzles(
                tenant_id=tenant_id, filters=filters, limit=limit, cursor=cursor
            )
        except Exception as exc:  # noqa: BLE001
            if "cursor" in str(exc).lower() or isinstance(exc, (ValueError, IndexError)):
                raise HTTPException(status_code=422, detail="Invalid cursor") from exc
            raise
        return ChessPuzzlePageResponse(
            items=[ChessPuzzleResponse.model_validate(p) for p in page.items],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )

    async def get_puzzle(
        self, *, tenant_id: uuid.UUID, puzzle_id: uuid.UUID
    ) -> ChessPuzzleResponse:
        puzzle = await self.queries.get_puzzle(tenant_id=tenant_id, puzzle_id=puzzle_id)
        if puzzle is None:
            raise HTTPException(status_code=404, detail="Puzzle not found")
        return ChessPuzzleResponse.model_validate(puzzle)

    async def get_daily_puzzle(self, *, tenant_id: uuid.UUID) -> ChessDailyPuzzleResponse:
        """Local-first daily puzzle read — never calls providers (§9 / §10).

        Prefer today's ``daily_utc`` row; else last synced daily (stale + metadata);
        else 404 so callers can trigger an admin/job refresh.
        """
        day_utc = utc_day()
        local = await self.puzzles.get_daily_for_day(tenant_id=tenant_id, day_utc=day_utc)
        if local is not None:
            return daily_puzzle_response(local, today_utc=day_utc)

        stale = await self.puzzles.get_latest_daily(tenant_id=tenant_id)
        if stale is not None:
            return daily_puzzle_response(stale, today_utc=day_utc)

        raise HTTPException(
            status_code=404,
            detail="Daily puzzle not in local catalog yet — run daily puzzle sync",
        )

    async def sync_daily_puzzle(self, *, tenant_id: uuid.UUID) -> ChessDailyPuzzleResponse:
        """Background/admin refresh: fetch Lichess daily → upsert local catalog.

        Not used by normal GET ``/puzzles/daily`` (§9 / §10 hybrid model).
        """
        day_utc = utc_day()
        provider = get_puzzle_provider()
        try:
            external = await provider.get_daily_puzzle()
            built = normalize_external_puzzle(tenant_id=tenant_id, external=external)
            now = datetime.now(timezone.utc)
            built.retrieved_at = now
            built.license_note = built.license_note or license_for_provider(built.provider)
            built.source_metadata = stamp_ingestion_mode(
                {
                    **dict(built.source_metadata or {}),
                    "daily_utc": day_utc,
                    "via": "daily_puzzle_sync",
                },
                ChessIngestionMode.PUZZLE_SYNC,
            )
            existing = await self.puzzles.get_by_provider_external_id(
                tenant_id=tenant_id,
                provider=built.provider,
                external_id=built.external_id,
            )
            if existing is None:
                try:
                    async with self.db.begin_nested():
                        await self.puzzles.add(built)
                    puzzle: ChessPuzzle = built
                except IntegrityError:
                    # Concurrent daily sync / same provider+external — reuse winner.
                    raced = await self.puzzles.get_by_provider_external_id(
                        tenant_id=tenant_id,
                        provider=built.provider,
                        external_id=built.external_id,
                    )
                    if raced is None:
                        raise
                    raced.retrieved_at = now
                    raced.source_metadata = stamp_ingestion_mode(
                        {
                            **dict(raced.source_metadata or {}),
                            "daily_utc": day_utc,
                            "via": "daily_puzzle_sync",
                        },
                        ChessIngestionMode.PUZZLE_SYNC,
                    )
                    puzzle = raced
            else:
                if existing.license_note is None:
                    existing.license_note = built.license_note
                existing.retrieved_at = now
                existing.source_metadata = stamp_ingestion_mode(
                    {
                        **dict(existing.source_metadata or {}),
                        "daily_utc": day_utc,
                        "via": "daily_puzzle_sync",
                    },
                    ChessIngestionMode.PUZZLE_SYNC,
                )
                puzzle = existing
        except Exception as exc:  # noqa: BLE001 — map known classes; re-raise unknown
            mapped = http_exception_for_chess_failure(exc)
            if mapped is not None:
                raise mapped from exc
            raise
        return daily_puzzle_response(puzzle, today_utc=day_utc)

"""Chess catalog search / import / daily puzzle application service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.catalog_queries import (
    ChessCatalogQuery,
    GameSearchFilters,
    PuzzleSearchFilters,
)
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.licenses import license_for_provider
from backend.modules.chess_intelligence.models import ChessPuzzle
from backend.modules.chess_intelligence.moves import annotate_moves
from backend.modules.chess_intelligence.normalizer import (
    chess_game_from_parsed,
    normalize_external_puzzle,
)
from backend.modules.chess_intelligence.providers.http_errors import (
    http_exception_for_chess_failure,
)
from backend.modules.chess_intelligence.providers.lichess_puzzles import LichessPuzzlesProvider
from backend.modules.chess_intelligence.repository import ChessPuzzleRepository
from backend.modules.chess_intelligence.schemas import (
    AnnotatedChessMoveSchema,
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
            items=[ChessGameResponse.model_validate(g) for g in page.items],
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        )

    async def get_game(self, *, tenant_id: uuid.UUID, game_id: uuid.UUID) -> ChessGameResponse:
        game = await self.queries.get_game(tenant_id=tenant_id, game_id=game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")
        return ChessGameResponse.model_validate(game)

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
                source_metadata={"via": "chess_search_api"},
                license_note=license_for_provider(provider) or license_for_provider("api_import"),
                retrieved_at=datetime.now(timezone.utc),
            ),
        )
        return ChessGameImportResponse(
            game=ChessGameResponse.model_validate(outcome.game),
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

    async def get_daily_puzzle(self, *, tenant_id: uuid.UUID) -> ChessPuzzleResponse:
        """Fetch Lichess daily, upsert into catalog, return canonical row."""
        provider = LichessPuzzlesProvider()
        try:
            external = await provider.get_daily_puzzle()
            built = normalize_external_puzzle(tenant_id=tenant_id, external=external)
            now = datetime.now(timezone.utc)
            built.retrieved_at = now
            built.license_note = built.license_note or license_for_provider(built.provider)
            existing = await self.puzzles.get_by_provider_external_id(
                tenant_id=tenant_id,
                provider=built.provider,
                external_id=built.external_id,
            )
            if existing is None:
                await self.puzzles.add(built)
                puzzle: ChessPuzzle = built
            else:
                if existing.license_note is None:
                    existing.license_note = built.license_note
                existing.retrieved_at = now
                puzzle = existing
        except Exception as exc:  # noqa: BLE001 — map known classes; re-raise unknown
            mapped = http_exception_for_chess_failure(exc)
            if mapped is not None:
                raise mapped from exc
            raise
        return ChessPuzzleResponse.model_validate(puzzle)

"""Build provenance traces: content → catalog → provider → original PGN/data."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.catalog_queries import ChessCatalogQuery
from backend.modules.chess_intelligence.licenses import license_for_provider
from backend.modules.chess_intelligence.models import ChessGameSource
from backend.modules.chess_intelligence.provenance_schemas import (
    ChessGameProvenanceResponse,
    ChessPuzzleProvenanceResponse,
    ChessSourceRecordSchema,
    ChessVideoProvenanceResponse,
)
from backend.modules.chess_intelligence.repository import ChessGameRepository
from backend.modules.chess_video.repository import ChessVideoRepository


def _source_schema(row: ChessGameSource) -> ChessSourceRecordSchema:
    """Serialize a source row; fill known license notes when the column is blank."""
    schema = ChessSourceRecordSchema.model_validate(row)
    if not schema.license_note:
        schema = schema.model_copy(
            update={"license_note": license_for_provider(schema.provider)}
        )
    return schema


class ChessProvenanceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.queries = ChessCatalogQuery(db)
        self.games = ChessGameRepository(db)
        self.videos = ChessVideoRepository(db)

    async def for_game(
        self, *, tenant_id: uuid.UUID, game_id: uuid.UUID
    ) -> ChessGameProvenanceResponse:
        game = await self.queries.get_game(tenant_id=tenant_id, game_id=game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")
        rows = await self.games.list_sources_for_game(
            tenant_id=tenant_id, chess_game_id=game_id
        )
        sources = [_source_schema(r) for r in rows]
        primary = next((s for s in sources if s.is_primary), None)
        if primary is None and sources:
            primary = sources[0]
        if primary is None and game.source_provider:
            primary = ChessSourceRecordSchema(
                provider=game.source_provider,
                external_id=game.source_external_id,
                source_url=game.source_url,
                source_metadata=dict(game.source_metadata or {}),
                license_note=license_for_provider(game.source_provider),
                is_primary=True,
            )
            sources = [primary]
        return ChessGameProvenanceResponse(
            chess_game_id=game.id,
            normalized_pgn=game.normalized_pgn,
            content_hash=game.content_hash,
            game_fingerprint=game.game_fingerprint,
            primary_source=primary,
            sources=sources,
        )

    async def for_puzzle(
        self, *, tenant_id: uuid.UUID, puzzle_id: uuid.UUID
    ) -> ChessPuzzleProvenanceResponse:
        puzzle = await self.queries.get_puzzle(tenant_id=tenant_id, puzzle_id=puzzle_id)
        if puzzle is None:
            raise HTTPException(status_code=404, detail="Puzzle not found")
        license_note = puzzle.license_note or license_for_provider(puzzle.provider)
        return ChessPuzzleProvenanceResponse(
            chess_puzzle_id=puzzle.id,
            provider=puzzle.provider,
            external_id=puzzle.external_id,
            starting_fen=puzzle.starting_fen,
            solution_moves_uci=list(puzzle.solution_moves_uci or []),
            source_game_id=puzzle.source_game_id,
            source_game_url=puzzle.source_game_url,
            source_metadata=dict(puzzle.source_metadata or {}),
            import_batch_id=puzzle.import_batch_id,
            license_note=license_note,
            retrieved_at=puzzle.retrieved_at,
            content_hash=puzzle.content_hash,
            puzzle_fingerprint=puzzle.puzzle_fingerprint,
        )

    async def for_video(
        self, *, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> ChessVideoProvenanceResponse:
        job = await self.videos.get_for_tenant(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Chess video job not found")
        game_trace = None
        if job.chess_game_id is not None:
            game_trace = await self.for_game(
                tenant_id=tenant_id, game_id=job.chess_game_id
            )
        return ChessVideoProvenanceResponse(
            chess_video_job_id=job.id,
            chess_game_id=job.chess_game_id,
            normalized_pgn=job.normalized_pgn,
            source_hash=job.source_hash,
            game=game_trace,
        )

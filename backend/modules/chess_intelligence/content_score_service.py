"""Content opportunity score read/compute helpers."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.catalog_queries import ChessCatalogQuery
from backend.modules.chess_intelligence.content_opportunity import score_from_entities
from backend.modules.chess_intelligence.models import ChessContentOpportunityScore
from backend.modules.chess_intelligence.schemas import ChessContentOpportunityScoreSchema


async def latest_content_score(
    db: AsyncSession, *, tenant_id: uuid.UUID, game_id: uuid.UUID
) -> ChessContentOpportunityScoreSchema:
    game = await ChessCatalogQuery(db).get_game(tenant_id=tenant_id, game_id=game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    result = await db.execute(
        select(ChessContentOpportunityScore)
        .where(
            ChessContentOpportunityScore.tenant_id == tenant_id,
            ChessContentOpportunityScore.chess_game_id == game_id,
        )
        .order_by(ChessContentOpportunityScore.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return ChessContentOpportunityScoreSchema.model_validate(row).model_copy(
            update={"persisted": True}
        )
    computed = score_from_entities(
        game=game, moment_classifications=[], tactical_patterns=[]
    )
    return ChessContentOpportunityScoreSchema(
        id=None,
        chess_game_id=game_id,
        analysis_job_id=None,
        score=computed.score,
        components=computed.components,
        reasons=computed.reasons,
        formula_version=computed.formula_version,
        created_at=None,
        updated_at=None,
        persisted=False,
    )

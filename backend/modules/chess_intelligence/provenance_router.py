"""HTTP routes for chess source provenance (Phase 19)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import require_permission
from backend.api.deps.db import get_db
from backend.modules.chess_intelligence.provenance_schemas import (
    ChessGameProvenanceResponse,
    ChessPuzzleProvenanceResponse,
)
from backend.modules.chess_intelligence.provenance_service import ChessProvenanceService
from backend.modules.identity_access.models import TenantUser

router = APIRouter()


@router.get("/games/{game_id}/provenance", response_model=ChessGameProvenanceResponse)
async def get_game_provenance(
    game_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessGameProvenanceResponse:
    return await ChessProvenanceService(db).for_game(
        tenant_id=membership.tenant_id, game_id=game_id
    )


@router.get("/puzzles/{puzzle_id}/provenance", response_model=ChessPuzzleProvenanceResponse)
async def get_puzzle_provenance(
    puzzle_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessPuzzleProvenanceResponse:
    return await ChessProvenanceService(db).for_puzzle(
        tenant_id=membership.tenant_id, puzzle_id=puzzle_id
    )

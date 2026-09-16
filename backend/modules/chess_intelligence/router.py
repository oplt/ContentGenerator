"""Chess catalog search API — `/api/v1/chess/*`."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import require_permission
from backend.api.deps.db import get_db
from backend.modules.chess_intelligence.analysis_service import ChessAnalysisService
from backend.modules.chess_intelligence.catalog_queries import (
    GameSearchFilters,
    PuzzleSearchFilters,
)
from backend.modules.chess_intelligence.schemas import (
    AnnotatedChessMoveSchema,
    ChessAnalysisJobResponse,
    ChessAnalysisRequest,
    ChessContentOpportunityScoreSchema,
    ChessGameImportRequest,
    ChessGameImportResponse,
    ChessGamePageResponse,
    ChessGameResponse,
    ChessGameVideoRequest,
    ChessPuzzlePageResponse,
    ChessPuzzleResponse,
)
from backend.modules.chess_intelligence.service import ChessCatalogService
from backend.modules.chess_video.models import ChessVideoJobStatus
from backend.modules.chess_video.schemas import ChessVideoCreateRequest, ChessVideoJobResponse
from backend.modules.chess_video.service import ChessVideoService
from backend.modules.identity_access.models import TenantUser

router = APIRouter()


@router.get("/games", response_model=ChessGamePageResponse)
async def list_games(
    player: str | None = Query(default=None),
    white: str | None = Query(default=None, alias="white_player"),
    black: str | None = Query(default=None, alias="black_player"),
    year_from: int | None = Query(default=None, ge=1400, le=2100),
    year_to: int | None = Query(default=None, ge=1400, le=2100),
    event: str | None = Query(default=None),
    result: str | None = Query(default=None),
    opening: str | None = Query(default=None),
    eco: str | None = Query(default=None),
    famous_only: bool = Query(default=False),
    provider: str | None = Query(default=None),
    min_rating: int | None = Query(default=None, ge=0, le=4000),
    max_rating: int | None = Query(default=None, ge=0, le=4000),
    tag: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessGamePageResponse:
    return await ChessCatalogService(db).list_games(
        tenant_id=membership.tenant_id,
        filters=GameSearchFilters(
            player=player,
            white=white,
            black=black,
            year_from=year_from,
            year_to=year_to,
            event=event,
            result=result,
            opening=opening,
            eco=eco,
            famous_only=famous_only,
            provider=provider,
            min_rating=min_rating,
            max_rating=max_rating,
            tag=tag,
        ),
        limit=limit,
        cursor=cursor,
    )


@router.get("/games/famous", response_model=ChessGamePageResponse)
async def list_famous_games(
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessGamePageResponse:
    return await ChessCatalogService(db).list_games(
        tenant_id=membership.tenant_id,
        filters=GameSearchFilters(famous_only=True),
        limit=limit,
        cursor=cursor,
    )


@router.post("/games/import", response_model=ChessGameImportResponse, status_code=201)
async def import_game(
    payload: ChessGameImportRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessGameImportResponse:
    result = await ChessCatalogService(db).import_game(
        tenant_id=membership.tenant_id, payload=payload
    )
    await db.commit()
    return result


@router.get("/games/{game_id}", response_model=ChessGameResponse)
async def get_game(
    game_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessGameResponse:
    return await ChessCatalogService(db).get_game(
        tenant_id=membership.tenant_id, game_id=game_id
    )


@router.get("/games/{game_id}/moves", response_model=list[AnnotatedChessMoveSchema])
async def get_game_moves(
    game_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> list[AnnotatedChessMoveSchema]:
    return await ChessCatalogService(db).get_game_moves(
        tenant_id=membership.tenant_id, game_id=game_id
    )


@router.post(
    "/games/{game_id}/video",
    response_model=ChessVideoJobResponse,
    status_code=201,
)
async def create_video_from_game(
    game_id: UUID,
    payload: ChessGameVideoRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessVideoJobResponse:
    """Bridge catalog game → existing ChessVideoService (no second renderer)."""
    # Ensure game exists in-tenant before create resolves PGN.
    await ChessCatalogService(db).get_game(tenant_id=membership.tenant_id, game_id=game_id)
    video_svc = ChessVideoService(db)
    job = await video_svc.create(
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        payload=ChessVideoCreateRequest(
            chess_game_id=game_id,
            orientation=payload.orientation,
            render_preset=payload.render_preset,
            board_theme=payload.board_theme,
            seconds_per_move=payload.seconds_per_move,
            include_coordinates=payload.include_coordinates,
            include_move_text=payload.include_move_text,
            title=payload.title,
            subtitle=payload.subtitle,
        ),
    )
    await db.commit()
    await db.refresh(job)
    if job.status == ChessVideoJobStatus.QUEUED.value:
        video_svc.enqueue_job(tenant_id=membership.tenant_id, job_id=job.id)
    return ChessVideoJobResponse.model_validate(job)


@router.post(
    "/games/{game_id}/analyze",
    response_model=ChessAnalysisJobResponse,
    status_code=202,
)
async def enqueue_game_analysis(
    game_id: UUID,
    payload: ChessAnalysisRequest | None = None,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessAnalysisJobResponse:
    """Queue Stockfish analysis (Celery). Does not run the engine in-request."""
    svc = ChessAnalysisService(db)
    job = await svc.enqueue(
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        game_id=game_id,
        payload=payload or ChessAnalysisRequest(),
    )
    await db.commit()
    await db.refresh(job)
    svc.enqueue_celery(tenant_id=membership.tenant_id, job_id=job.id)
    return ChessAnalysisService._to_response(job, [])


@router.get("/games/{game_id}/analysis", response_model=ChessAnalysisJobResponse)
async def get_latest_game_analysis(
    game_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessAnalysisJobResponse:
    result = await ChessAnalysisService(db).latest_for_game(
        tenant_id=membership.tenant_id, game_id=game_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No analysis for this game")
    return result


@router.get("/games/{game_id}/content-score", response_model=ChessContentOpportunityScoreSchema)
async def get_game_content_score(
    game_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessContentOpportunityScoreSchema:
    """Latest persisted score, or metadata-only compute when no analysis yet."""
    result = await ChessAnalysisService(db).latest_content_score(
        tenant_id=membership.tenant_id, game_id=game_id
    )
    return result


@router.get("/analysis/{job_id}", response_model=ChessAnalysisJobResponse)
async def get_analysis_job(
    job_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessAnalysisJobResponse:
    return await ChessAnalysisService(db).get_job(
        tenant_id=membership.tenant_id, job_id=job_id
    )


@router.get("/puzzles", response_model=ChessPuzzlePageResponse)
async def list_puzzles(
    min_rating: int | None = Query(default=None, ge=0, le=4000),
    max_rating: int | None = Query(default=None, ge=0, le=4000),
    theme: str | None = Query(default=None),
    opening: str | None = Query(default=None),
    min_popularity: int | None = Query(default=None),
    provider: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessPuzzlePageResponse:
    return await ChessCatalogService(db).list_puzzles(
        tenant_id=membership.tenant_id,
        filters=PuzzleSearchFilters(
            min_rating=min_rating,
            max_rating=max_rating,
            theme=theme,
            opening=opening,
            min_popularity=min_popularity,
            provider=provider,
        ),
        limit=limit,
        cursor=cursor,
    )


@router.get("/puzzles/daily", response_model=ChessPuzzleResponse)
async def get_daily_puzzle(
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessPuzzleResponse:
    result = await ChessCatalogService(db).get_daily_puzzle(tenant_id=membership.tenant_id)
    await db.commit()
    return result


@router.get("/puzzles/{puzzle_id}", response_model=ChessPuzzleResponse)
async def get_puzzle(
    puzzle_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessPuzzleResponse:
    return await ChessCatalogService(db).get_puzzle(
        tenant_id=membership.tenant_id, puzzle_id=puzzle_id
    )

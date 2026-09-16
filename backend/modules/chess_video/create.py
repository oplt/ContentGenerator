"""Create chess video jobs — raw PGN/SAN/UCI or catalog ChessGame id."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import time
import uuid

from typing import Literal, cast

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.observability import record_video_handoff
from backend.modules.chess_video.fingerprint import compute_render_fingerprint
from backend.modules.chess_video.models import ChessVideoJob, ChessVideoJobStatus
from backend.modules.chess_video.parser import ChessParseError, parse_chess_input
from backend.modules.chess_video.presets import get_preset
from backend.modules.chess_video.renderer import RENDERER_VERSION
from backend.modules.chess_video.repository import ChessVideoRepository
from backend.modules.chess_video.schemas import ChessVideoCreateRequest
from backend.modules.chess_video.themes import get_board_theme


async def resolve_create_payload(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    payload: ChessVideoCreateRequest,
) -> tuple[ChessVideoCreateRequest, bool | None]:
    """Prefer catalog ``chess_game_id`` → local ``normalized_pgn``; else ``source_text``.

    §22 — never call providers here. Historical / recent / famous selection
    hands a catalog id; this loads PGN from the operational DB only.
    Manual PGN/SAN/UCI ``source_text`` remains supported.

    Returns ``(payload, is_famous)`` where ``is_famous`` is set when resolving a catalog game.
    """
    if payload.chess_game_id is None:
        if not payload.source_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide source_text or chess_game_id",
            )
        return payload, None

    from backend.modules.chess_intelligence.catalog_queries import ChessCatalogQuery

    game = await ChessCatalogQuery(db).get_game(
        tenant_id=tenant_id, game_id=payload.chess_game_id
    )
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    title = payload.title if payload.title is not None else game.famous_title
    subtitle = payload.subtitle
    if subtitle is None:
        white = game.white_player or "?"
        black = game.black_player or "?"
        subtitle = f"{white} vs {black}"
    return (
        payload.model_copy(
            update={
                "source_text": game.normalized_pgn,
                "input_format": "pgn",
                "title": title,
                "subtitle": subtitle,
            }
        ),
        bool(game.is_famous),
    )


async def create_video_job(
    db: AsyncSession,
    repo: ChessVideoRepository,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload: ChessVideoCreateRequest,
    copy_cached_outputs: Callable[[ChessVideoJob, ChessVideoJob], None],
) -> ChessVideoJob:
    started = time.perf_counter()
    resolved, is_famous = await resolve_create_payload(
        db, tenant_id=tenant_id, payload=payload
    )
    assert resolved.source_text is not None
    try:
        fmt = cast(Literal["pgn", "san", "uci", "auto"], resolved.input_format)
        game = parse_chess_input(resolved.source_text, fmt)
        get_preset(resolved.render_preset)
        get_board_theme(resolved.board_theme)
    except ChessParseError as exc:
        record_video_handoff(
            outcome="failure",
            source="paste" if payload.chess_game_id is None else "catalog",
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        record_video_handoff(
            outcome="failure",
            source="paste" if payload.chess_game_id is None else "catalog",
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    fingerprint = compute_render_fingerprint(
        normalized_pgn=game.normalized_pgn,
        starting_fen=game.starting_fen,
        orientation=resolved.orientation,
        render_preset=resolved.render_preset,
        seconds_per_move=resolved.seconds_per_move,
        include_coordinates=resolved.include_coordinates,
        include_move_text=resolved.include_move_text,
        title=resolved.title,
        board_theme=resolved.board_theme,
    )
    source_hash = hashlib.sha256(resolved.source_text.encode("utf-8")).hexdigest()
    cached = await repo.find_reusable_completed(
        tenant_id=tenant_id, render_fingerprint=fingerprint
    )
    job = ChessVideoJob(
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        status=ChessVideoJobStatus.QUEUED.value,
        stage=ChessVideoJobStatus.QUEUED.value,
        progress=0.0,
        input_format=game.input_format,
        source_text=resolved.source_text,
        normalized_pgn=game.normalized_pgn,
        source_hash=source_hash,
        chess_game_id=resolved.chess_game_id,
        white_player=game.white_player,
        black_player=game.black_player,
        event=game.event,
        game_date=game.date,
        result=game.result,
        starting_fen=game.starting_fen,
        move_count=game.move_count,
        orientation=resolved.orientation,
        render_preset=resolved.render_preset,
        board_theme=resolved.board_theme,
        seconds_per_move=resolved.seconds_per_move,
        include_coordinates=resolved.include_coordinates,
        include_move_text=resolved.include_move_text,
        title=resolved.title,
        subtitle=resolved.subtitle,
        renderer_version=RENDERER_VERSION,
        render_fingerprint=fingerprint,
    )
    if is_famous:
        source = "famous"
    elif payload.chess_game_id is not None:
        source = "catalog"
    else:
        source = "paste"
    duration_ms = (time.perf_counter() - started) * 1000.0
    if cached is not None and cached.video_public_url:
        copy_cached_outputs(job, cached)
        await repo.create(job)
        record_video_handoff(
            outcome="success",
            source=source,
            cached=True,
            is_famous=is_famous,
            duration_ms=duration_ms,
        )
        return job
    await repo.create(job)
    record_video_handoff(
        outcome="success",
        source=source,
        cached=False,
        is_famous=is_famous,
        duration_ms=duration_ms,
    )
    return job

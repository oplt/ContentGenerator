"""Provider sync + critical-moment re-extract runners."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.catalog_job_models import ChessCatalogJob
from backend.modules.chess_intelligence.catalog_queries import ChessCatalogQuery
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.engine.analyzer import PlyAnalysis
from backend.modules.chess_intelligence.engine.critical_moments import detect_critical_moments
from backend.modules.chess_intelligence.engine.tactical_patterns import detect_tactical_patterns
from backend.modules.chess_intelligence.licenses import license_for_provider
from backend.modules.chess_intelligence.models import (
    ChessCriticalMoment,
    ChessPositionAnalysis,
    ChessTacticalPattern,
)
from backend.modules.chess_intelligence.normalizer import normalize_external_game
from backend.modules.chess_intelligence.providers.chesscom import ChessComProvider
from backend.modules.chess_intelligence.providers.dtos import ChessGameSearchQuery
from backend.modules.chess_intelligence.providers.lichess_masters import LichessMastersProvider

logger = logging.getLogger(__name__)


async def touch(db: AsyncSession, job: ChessCatalogJob, *, progress: float, result: dict) -> None:
    job.progress = min(max(progress, 0.0), 0.99)
    job.result = result
    await db.flush()


async def extract_critical_moments(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    params = job.params or {}
    analysis_job_id = uuid.UUID(str(params["analysis_job_id"]))
    rows = list(
        (
            await db.execute(
                select(ChessPositionAnalysis)
                .where(ChessPositionAnalysis.analysis_job_id == analysis_job_id)
                .order_by(ChessPositionAnalysis.ply.asc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise ValueError("No position analyses for analysis_job_id")
    game_id = rows[0].chess_game_id
    if rows[0].tenant_id != job.tenant_id:
        raise ValueError("analysis_job_id does not belong to tenant")
    game = await ChessCatalogQuery(db).get_game(tenant_id=job.tenant_id, game_id=game_id)
    if game is None:
        raise ValueError("Catalog game not found for analysis")
    starting_fen = game.starting_fen
    plies = [
        PlyAnalysis(
            ply=r.ply,
            fen=r.fen,
            evaluation_cp=r.evaluation_cp,
            mate_in=r.mate_in,
            evaluation_before_cp=r.evaluation_before_cp,
            mate_before=r.mate_before,
            evaluation_after_cp=r.evaluation_after_cp,
            mate_after=r.mate_after,
            evaluation_delta=r.evaluation_delta,
            best_move_uci=r.best_move_uci,
            best_move_san=r.best_move_san,
            played_move_uci=r.played_move_uci,
            played_move_san=r.played_move_san,
            depth=r.depth,
            nodes=r.nodes,
            engine_name=r.engine_name or "",
            engine_version=r.engine_version or "",
        )
        for r in rows
    ]
    await db.execute(
        delete(ChessCriticalMoment).where(ChessCriticalMoment.analysis_job_id == analysis_job_id)
    )
    await db.execute(
        delete(ChessTacticalPattern).where(ChessTacticalPattern.analysis_job_id == analysis_job_id)
    )
    moments = detect_critical_moments(plies, starting_fen=starting_fen)
    for moment in moments:
        db.add(
            ChessCriticalMoment(
                tenant_id=job.tenant_id,
                chess_game_id=game_id,
                analysis_job_id=analysis_job_id,
                ply=moment.ply,
                classification=moment.classification,
                confidence=moment.confidence,
                detection_method=moment.detection_method,
                engine_facts=moment.engine_facts,
                heuristic_summary=moment.heuristic_summary,
            )
        )
    patterns = detect_tactical_patterns(plies, starting_fen=starting_fen)
    for pattern in patterns:
        db.add(
            ChessTacticalPattern(
                tenant_id=job.tenant_id,
                chess_game_id=game_id,
                analysis_job_id=analysis_job_id,
                ply=pattern.ply,
                pattern=pattern.pattern,
                confidence=pattern.confidence,
                detection_method=pattern.detection_method,
                facts=pattern.facts,
                summary=pattern.summary,
            )
        )
    await db.flush()
    return {
        "analysis_job_id": str(analysis_job_id),
        "chess_game_id": str(game_id),
        "moments": len(moments),
        "patterns": len(patterns),
        "plies": len(plies),
    }


async def provider_sync(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    params = job.params or {}
    provider_name = str(params["provider"])
    max_games = min(max(int(params.get("max_games") or 15), 1), 50)
    query = ChessGameSearchQuery(
        moves=params.get("moves"),
        fen=params.get("fen"),
        year_from=params.get("year_from"),
        year_to=params.get("year_to"),
        max_games=max_games,
        player=params.get("player"),
        white=params.get("white"),
        black=params.get("black"),
    )
    provider = (
        LichessMastersProvider() if provider_name == "lichess_masters" else ChessComProvider()
    )
    summaries = await provider.search_games(query)
    dedupe = ChessGameDedupeService(db)
    inserted = linked = dupes = errors = 0
    batch = summaries[:max_games]
    for i, summary in enumerate(batch):
        try:
            external = await provider.get_game(summary.external_id)
            game = normalize_external_game(tenant_id=job.tenant_id, external=external)
            source = SourceRef(
                provider=external.provider,
                external_id=external.external_id,
                source_url=external.source_url,
                source_metadata=dict(external.source_metadata or {}),
                import_batch_id=job.import_batch_id,
                license_note=license_for_provider(external.provider),
            )
            outcome = await dedupe.upsert_game(game=game, source=source)
            if outcome.created_game:
                inserted += 1
            elif outcome.created_source:
                linked += 1
            else:
                dupes += 1
        except Exception as exc:  # noqa: BLE001 — continue remaining games
            errors += 1
            logger.warning(
                "provider_sync_game_failed provider=%s id=%s err=%s",
                provider_name,
                summary.external_id,
                exc,
            )
        await touch(
            db,
            job,
            progress=0.1 + 0.8 * ((i + 1) / max(len(batch), 1)),
            result={
                "searched": len(summaries),
                "inserted": inserted,
                "linked_source": linked,
                "skipped_duplicate": dupes,
                "skipped_error": errors,
            },
        )
    await db.flush()
    return {
        "provider": provider_name,
        "searched": len(summaries),
        "inserted": inserted,
        "linked_source": linked,
        "skipped_duplicate": dupes,
        "skipped_error": errors,
    }

"""Provider sync + critical-moment re-extract runners."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.analysis_service import ChessAnalysisService
from backend.modules.chess_intelligence.catalog_job_models import ChessCatalogJob
from backend.modules.chess_intelligence.catalog_queries import ChessCatalogQuery
from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.discovery_eligibility import (
    evaluate_analysis_eligibility,
    policy_from_params,
)
from backend.modules.chess_intelligence.engine.analyzer import PlyAnalysis
from backend.modules.chess_intelligence.engine.critical_moments import detect_critical_moments
from backend.modules.chess_intelligence.engine.tactical_patterns import detect_tactical_patterns
from backend.modules.chess_intelligence.ingestion_mode import (
    ChessIngestionMode,
    stamp_ingestion_mode,
)
from backend.modules.chess_intelligence.licenses import license_for_provider
from backend.modules.chess_intelligence.models import (
    ChessCriticalMoment,
    ChessGame,
    ChessPositionAnalysis,
    ChessTacticalPattern,
)
from backend.modules.chess_intelligence.normalizer import normalize_external_game
from backend.modules.chess_intelligence.observability import (
    record_analysis_lifecycle,
    record_discovery_persistence,
    stats_from_provider_sync,
)
from backend.modules.chess_intelligence.operational_catalog import clamp_provider_sync_max_games
from backend.modules.chess_intelligence.provider_sync_state import (
    ChessProviderSyncStateService,
    compute_incremental_window,
    game_date_in_window,
)
from backend.modules.chess_intelligence.providers.dtos import ChessGameSearchQuery
from backend.modules.chess_intelligence.providers.registry import get_historical_game_provider
from fastapi import HTTPException

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
    record_analysis_lifecycle(
        event="analysis_completed",
        critical_moments=len(moments),
    )
    return {
        "analysis_job_id": str(analysis_job_id),
        "chess_game_id": str(game_id),
        "moments": len(moments),
        "patterns": len(patterns),
        "plies": len(plies),
        "critical_moments": len(moments),
        "content_opportunities_created": 0,
    }


async def provider_sync(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    """Incremental discovery → optional eligible Stockfish (§21) → checkpoint.

    Stockfish only when ``auto_analyze`` (config/job) and cheap eligibility pass.
    Never sets ``is_famous``. Analysis persist already writes moments/patterns/opportunity.
    """
    params = job.params or {}
    provider_name = str(params["provider"])
    max_games = clamp_provider_sync_max_games(params.get("max_games"))
    analysis_policy = policy_from_params(params)

    sync_svc = ChessProviderSyncStateService(db)
    sync_state = await sync_svc.get_or_create(
        tenant_id=job.tenant_id,
        provider=provider_name,
        params=params,
    )
    await sync_svc.mark_attempt(sync_state, job_id=job.id)

    window = compute_incremental_window(
        high_water_mark=sync_state.high_water_mark,
        lookback_seconds=sync_state.lookback_seconds,
        bootstrap_lookback_seconds=(
            int(params["bootstrap_lookback_seconds"])
            if params.get("bootstrap_lookback_seconds") is not None
            else None
        ),
        explicit_year_from=params.get("year_from"),
        explicit_year_to=params.get("year_to"),
    )

    query = ChessGameSearchQuery(
        moves=params.get("moves"),
        fen=params.get("fen"),
        year_from=window.year_from,
        year_to=window.year_to,
        max_games=max_games,
        player=params.get("player"),
        white=params.get("white"),
        black=params.get("black"),
    )
    provider = get_historical_game_provider(provider_name)
    started = time.perf_counter()
    summaries = await provider.search_games(query)
    in_window = [
        s
        for s in summaries
        if game_date_in_window(s.game_date, window=window, keep_unknown=True)
    ]
    dedupe = ChessGameDedupeService(db)
    analysis_svc = ChessAnalysisService(db) if analysis_policy.auto_analyze else None
    inserted = linked = dupes = errors = 0
    analysis_requested = analysis_reused = analysis_skipped = 0
    candidates: list[tuple[ChessGame, bool]] = []
    batch = in_window[:max_games]
    for i, summary in enumerate(batch):
        try:
            external = await provider.get_game(summary.external_id)
            game = normalize_external_game(tenant_id=job.tenant_id, external=external)
            # §21 — discovery never classifies fame.
            game.is_famous = False
            source = SourceRef(
                provider=external.provider,
                external_id=external.external_id,
                source_url=external.source_url,
                source_metadata=stamp_ingestion_mode(
                    {
                        **dict(external.source_metadata or {}),
                        "sync_window_start": window.window_start.isoformat(),
                        "sync_window_end": window.window_end.isoformat(),
                    },
                    ChessIngestionMode.RECENT_DISCOVERY,
                ),
                import_batch_id=job.import_batch_id,
                license_note=license_for_provider(external.provider),
            )
            outcome = await dedupe.upsert_game(game=game, source=source)
            if outcome.created_game:
                inserted += 1
                candidates.append((outcome.game, True))
            elif outcome.created_source:
                linked += 1
                if not analysis_policy.new_games_only:
                    candidates.append((outcome.game, False))
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
            progress=0.1 + 0.7 * ((i + 1) / max(len(batch), 1)),
            result={
                "searched": len(summaries),
                "in_window": len(in_window),
                "inserted": inserted,
                "linked_source": linked,
                "skipped_duplicate": dupes,
                "skipped_error": errors,
                "discovered": len(summaries),
                "new_games": inserted,
                "failed": errors,
                "auto_analyze": analysis_policy.auto_analyze,
                "sync_state_id": str(sync_state.id),
                "window": window.as_dict(),
            },
        )

    if analysis_svc is not None:
        for game, created in candidates:
            if analysis_requested >= analysis_policy.max_analyze_per_sync:
                analysis_skipped += 1
                continue
            decision = evaluate_analysis_eligibility(
                game, analysis_policy, created_game=created
            )
            if not decision.eligible:
                analysis_skipped += 1
                continue
            try:
                enq = await analysis_svc.enqueue(
                    tenant_id=job.tenant_id,
                    user_id=None,
                    game_id=game.id,
                )
                if enq.reused:
                    analysis_reused += 1
                else:
                    analysis_requested += 1
                if enq.should_dispatch:
                    analysis_svc.enqueue_celery(
                        tenant_id=job.tenant_id, job_id=enq.job.id
                    )
            except HTTPException as exc:
                analysis_skipped += 1
                logger.info(
                    "provider_sync_analyze_skipped game=%s status=%s detail=%s",
                    game.id,
                    exc.status_code,
                    exc.detail,
                )
            except Exception as exc:  # noqa: BLE001
                analysis_skipped += 1
                logger.warning(
                    "provider_sync_analyze_failed game=%s err=%s", game.id, exc
                )

    duration_ms = (time.perf_counter() - started) * 1000.0
    hwm_before = (
        window.high_water_mark_before.isoformat() if window.high_water_mark_before else None
    )
    stats = stats_from_provider_sync(
        searched=len(summaries),
        in_window=len(in_window),
        attempted=len(batch),
        inserted=inserted,
        linked=linked,
        dupes=dupes,
        errors=errors,
        duration_ms=duration_ms,
        high_water_mark=hwm_before,
        sync_state_id=str(sync_state.id),
        sync_key=sync_state.sync_key,
        query_hash=sync_state.query_hash,
        lookback_seconds=sync_state.lookback_seconds,
        window=window.as_dict(),
        high_water_mark_before=hwm_before,
        provider=provider_name,
        ingestion_mode=ChessIngestionMode.RECENT_DISCOVERY.value,
        auto_analyze=analysis_policy.auto_analyze,
        analysis_skipped_ineligible=analysis_skipped,
        sets_famous=False,
    )
    stats.analysis_requested = analysis_requested
    stats.analysis_reused = analysis_reused
    result = stats.as_result()

    if errors == 0:
        await sync_svc.mark_success(
            sync_state,
            job_id=job.id,
            high_water_mark=window.window_end,
            state_metadata={
                "last_searched": len(summaries),
                "last_in_window": len(in_window),
                "last_inserted": inserted,
                "last_linked": linked,
                "last_dupes": dupes,
                "last_analysis_requested": analysis_requested,
                "last_window": window.as_dict(),
            },
        )
        result["sync_advanced"] = True
        result["high_water_mark"] = (
            sync_state.high_water_mark.isoformat() if sync_state.high_water_mark else None
        )
        stats.high_water_mark = result["high_water_mark"]
    else:
        await sync_svc.mark_failure(
            sync_state,
            job_id=job.id,
            error_summary=f"{errors} game fetch/normalize failures of {len(batch)} attempted",
        )
        result["sync_advanced"] = False
        result["high_water_mark"] = hwm_before

    record_discovery_persistence(kind="game", provider=provider_name, stats=stats)
    await db.flush()
    return result

"""Kind-specific runners for ChessCatalogJob (Phase 24)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.catalog_job_models import (
    ChessCatalogJob,
    ChessCatalogJobKind,
)
from backend.modules.chess_intelligence.catalog_job_sync import (
    extract_critical_moments,
    provider_sync,
    touch,
)
from backend.modules.chess_intelligence.famous_service import FamousCatalogService
from backend.modules.chess_intelligence.importers import (
    LichessPuzzleDatasetImporter,
    LichessPuzzleImportConfig,
    PgnArchiveImportConfig,
    PgnArchiveImporter,
)
from backend.modules.chess_intelligence.import_manifest import (
    attach_manifest_to_result,
    build_archive_manifest,
)
from backend.modules.chess_intelligence.ingestion_mode import mode_for_catalog_job_kind
from backend.modules.chess_intelligence.observability import (
    record_discovery_persistence,
    stats_from_pgn_progress,
    stats_from_puzzle_progress,
)
from backend.modules.chess_intelligence.operational_catalog import filters_from_params
from backend.modules.chess_intelligence.puzzle_catalog import puzzle_filters_from_params
from backend.modules.chess_intelligence.service import ChessCatalogService


async def run_catalog_job_body(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    kind = job.kind
    if kind == ChessCatalogJobKind.PGN_IMPORT.value:
        result = await _pgn_import(db, job)
    elif kind == ChessCatalogJobKind.PUZZLE_IMPORT.value:
        result = await _puzzle_import(db, job)
    elif kind == ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value:
        result = await _daily_puzzle_sync(db, job)
    elif kind == ChessCatalogJobKind.ENRICH_FAMOUS.value:
        result = await _enrich_famous(db, job)
    elif kind == ChessCatalogJobKind.EXTRACT_CRITICAL_MOMENTS.value:
        result = await extract_critical_moments(db, job)
    elif kind == ChessCatalogJobKind.PROVIDER_SYNC.value:
        result = await provider_sync(db, job)
    else:
        raise ValueError(f"Unsupported job kind: {kind}")
    mode = mode_for_catalog_job_kind(kind)
    if mode is not None and "ingestion_mode" not in result:
        result = {**result, "ingestion_mode": mode.value}
    return result


async def _pgn_import(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    params = job.params or {}
    path = Path(str(params["file_path"]))
    if not path.is_file():
        raise FileNotFoundError(f"PGN file not found: {path}")
    started = datetime.now(timezone.utc).isoformat()
    provider = str(params.get("provider") or "pgn_archive")
    source_name = str(params.get("source_name") or "archive")
    manifest = build_archive_manifest(
        path=path,
        provider=provider,
        source_name=source_name,
        import_batch_id=job.import_batch_id,
        source_uri=params.get("source_uri"),
        archive_version=params.get("archive_version"),
    )
    # Persist digest on the job for audits without a separate manifest table.
    job.params = {
        **dict(params),
        "archive_sha256": manifest.checksum_sha256,
        "archive_bytes": manifest.size_bytes,
        "archive_uri": manifest.source_uri,
    }
    config = PgnArchiveImportConfig(
        tenant_id=job.tenant_id,
        file_path=path,
        provider=provider,
        source_name=source_name,
        batch_size=max(int(params.get("batch_size") or 100), 1),
        dry_run=bool(params.get("dry_run") or False),
        skip_games=max(int(params.get("skip_games") or 0), 0),
        max_games=params.get("max_games"),
        import_batch_id=job.import_batch_id,
        license_note=params.get("license_note"),
        archive_sha256=manifest.checksum_sha256,
        archive_bytes=manifest.size_bytes,
        archive_uri=manifest.source_uri,
        archive_version=manifest.archive_version,
        filters=filters_from_params(params),
    )

    async def on_batch(progress: Any) -> None:
        await touch(
            db,
            job,
            progress=0.1 + min(0.85, progress.batches_committed * 0.02),
            result={
                "scanned": progress.scanned,
                "inserted": progress.inserted,
                "linked_source": progress.linked_source,
                "skipped_duplicate": progress.skipped_duplicate,
                "skipped_filtered": progress.skipped_filtered,
                "skipped_error": progress.skipped_error,
                "batches_committed": progress.batches_committed,
                "archive_sha256": manifest.checksum_sha256,
            },
        )

    progress = await PgnArchiveImporter(db).run(config, on_batch=on_batch)
    completed = datetime.now(timezone.utc).isoformat()
    stats = stats_from_pgn_progress(
        scanned=progress.scanned,
        inserted=progress.inserted,
        linked_source=progress.linked_source,
        skipped_duplicate=progress.skipped_duplicate,
        skipped_filtered=progress.skipped_filtered,
        skipped_error=progress.skipped_error,
        batches_committed=progress.batches_committed,
        error_samples=list(progress.error_samples),
    )
    record_discovery_persistence(
        kind="game",
        provider=provider,
        stats=stats,
        include_import_counters=False,
    )
    return attach_manifest_to_result(
        stats.as_result(),
        manifest,
        import_started_at=started,
        import_completed_at=completed,
    )


async def _puzzle_import(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    params = job.params or {}
    path = Path(str(params["file_path"]))
    if not path.is_file():
        raise FileNotFoundError(f"Puzzle file not found: {path}")
    started = datetime.now(timezone.utc).isoformat()
    themes = params.get("themes") or []
    if isinstance(themes, str):
        themes = [t.strip() for t in themes.split(",") if t.strip()]
    openings = params.get("openings") or params.get("opening") or []
    if isinstance(openings, str):
        openings = [t.strip() for t in openings.replace(",", " ").split() if t.strip()]
    puzzle_filters = puzzle_filters_from_params(params)
    manifest = build_archive_manifest(
        path=path,
        provider="lichess_puzzles",
        source_name=str(params.get("source_name") or "lichess_puzzle_db"),
        import_batch_id=job.import_batch_id,
        source_uri=params.get("source_uri"),
        archive_version=params.get("archive_version"),
    )
    job.params = {
        **dict(params),
        "archive_sha256": manifest.checksum_sha256,
        "archive_bytes": manifest.size_bytes,
        "archive_uri": manifest.source_uri,
    }
    config = LichessPuzzleImportConfig(
        tenant_id=job.tenant_id,
        file_path=path,
        batch_size=max(int(params.get("batch_size") or 200), 1),
        dry_run=bool(params.get("dry_run") or False),
        limit=params.get("limit"),
        min_rating=puzzle_filters.min_rating,
        max_rating=puzzle_filters.max_rating,
        min_popularity=puzzle_filters.min_popularity,
        themes=list(themes) or list(puzzle_filters.themes),
        openings=list(openings) or list(puzzle_filters.openings),
        daily_date_from=puzzle_filters.daily_date_from,
        daily_date_to=puzzle_filters.daily_date_to,
        providers=puzzle_filters.providers,
        import_batch_id=job.import_batch_id,
    )

    async def on_batch(progress: Any) -> None:
        await touch(
            db,
            job,
            progress=0.1 + min(0.85, progress.batches_committed * 0.02),
            result={
                "scanned": progress.scanned,
                "inserted": progress.inserted,
                "skipped_duplicate": progress.skipped_duplicate,
                "skipped_error": progress.skipped_error,
                "filtered": progress.filtered,
                "batches_committed": progress.batches_committed,
                "archive_sha256": manifest.checksum_sha256,
            },
        )

    progress = await LichessPuzzleDatasetImporter(db).run(config, on_batch=on_batch)
    completed = datetime.now(timezone.utc).isoformat()
    stats = stats_from_puzzle_progress(
        scanned=progress.scanned,
        inserted=progress.inserted,
        skipped_duplicate=progress.skipped_duplicate,
        filtered=progress.filtered,
        skipped_error=progress.skipped_error,
        batches_committed=progress.batches_committed,
        error_samples=list(progress.error_samples),
        creates_chess_games=False,
    )
    record_discovery_persistence(
        kind="puzzle",
        provider="lichess_puzzles",
        stats=stats,
        include_import_counters=False,
    )
    return attach_manifest_to_result(
        stats.as_result(),
        manifest,
        import_started_at=started,
        import_completed_at=completed,
    )


async def _daily_puzzle_sync(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    """Admin/scheduled refresh: Lichess daily → local ChessPuzzle (not a GET path)."""
    await touch(db, job, progress=0.2, result={"phase": "fetch_daily"})
    puzzle = await ChessCatalogService(db).sync_daily_puzzle(tenant_id=job.tenant_id)
    return {
        "puzzle_id": str(puzzle.id),
        "external_id": puzzle.external_id,
        "provider": puzzle.provider,
        "daily_utc": (puzzle.source_metadata or {}).get("daily_utc"),
    }


async def _enrich_famous(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    """Editorial metadata only — never fetches provider PGN / never recreates games."""
    params = job.params or {}
    report = await FamousCatalogService(db).apply_to_tenant(
        tenant_id=job.tenant_id,
        dry_run=bool(params.get("dry_run") or False),
        min_score=int(params.get("min_score") or 70),
        limit=int(params.get("limit") or 5000),
    )
    return {
        "scanned": report.scanned,
        "matched": report.matched,
        "updated": report.updated,
        "skipped_low_score": report.skipped_low_score,
        "curation_only": True,
        "downloads_pgn": False,
    }

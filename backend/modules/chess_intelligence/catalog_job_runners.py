"""Kind-specific runners for ChessCatalogJob (Phase 24)."""

from __future__ import annotations

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


async def run_catalog_job_body(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    kind = job.kind
    if kind == ChessCatalogJobKind.PGN_IMPORT.value:
        return await _pgn_import(db, job)
    if kind == ChessCatalogJobKind.PUZZLE_IMPORT.value:
        return await _puzzle_import(db, job)
    if kind == ChessCatalogJobKind.ENRICH_FAMOUS.value:
        return await _enrich_famous(db, job)
    if kind == ChessCatalogJobKind.EXTRACT_CRITICAL_MOMENTS.value:
        return await extract_critical_moments(db, job)
    if kind == ChessCatalogJobKind.PROVIDER_SYNC.value:
        return await provider_sync(db, job)
    raise ValueError(f"Unsupported job kind: {kind}")


async def _pgn_import(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    params = job.params or {}
    path = Path(str(params["file_path"]))
    if not path.is_file():
        raise FileNotFoundError(f"PGN file not found: {path}")
    config = PgnArchiveImportConfig(
        tenant_id=job.tenant_id,
        file_path=path,
        provider=str(params.get("provider") or "pgn_archive"),
        source_name=str(params.get("source_name") or "archive"),
        batch_size=max(int(params.get("batch_size") or 100), 1),
        dry_run=bool(params.get("dry_run") or False),
        skip_games=max(int(params.get("skip_games") or 0), 0),
        max_games=params.get("max_games"),
        import_batch_id=job.import_batch_id,
        license_note=params.get("license_note"),
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
                "skipped_error": progress.skipped_error,
                "batches_committed": progress.batches_committed,
            },
        )

    progress = await PgnArchiveImporter(db).run(config, on_batch=on_batch)
    return {
        "scanned": progress.scanned,
        "inserted": progress.inserted,
        "linked_source": progress.linked_source,
        "skipped_duplicate": progress.skipped_duplicate,
        "skipped_error": progress.skipped_error,
        "batches_committed": progress.batches_committed,
        "error_samples": list(progress.error_samples),
    }


async def _puzzle_import(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
    params = job.params or {}
    path = Path(str(params["file_path"]))
    if not path.is_file():
        raise FileNotFoundError(f"Puzzle file not found: {path}")
    themes = params.get("themes") or []
    if isinstance(themes, str):
        themes = [t.strip() for t in themes.split(",") if t.strip()]
    config = LichessPuzzleImportConfig(
        tenant_id=job.tenant_id,
        file_path=path,
        batch_size=max(int(params.get("batch_size") or 200), 1),
        dry_run=bool(params.get("dry_run") or False),
        limit=params.get("limit"),
        min_rating=params.get("min_rating"),
        max_rating=params.get("max_rating"),
        min_popularity=params.get("min_popularity"),
        themes=list(themes),
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
            },
        )

    progress = await LichessPuzzleDatasetImporter(db).run(config, on_batch=on_batch)
    return {
        "scanned": progress.scanned,
        "inserted": progress.inserted,
        "skipped_duplicate": progress.skipped_duplicate,
        "skipped_error": progress.skipped_error,
        "filtered": progress.filtered,
        "batches_committed": progress.batches_committed,
        "error_samples": list(progress.error_samples),
    }


async def _enrich_famous(db: AsyncSession, job: ChessCatalogJob) -> dict[str, Any]:
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
    }

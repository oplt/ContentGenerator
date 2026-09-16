"""Apply famous-game catalog metadata onto tenant ChessGame rows.

Local curation only — matches YAML entries to existing catalog games.
Does not download PGN from providers and does not create a parallel FamousGame table.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.famous_catalog import (
    DEFAULT_MIN_SCORE,
    FamousApplyReport,
    FamousGameEntry,
    apply_famous_metadata,
    best_famous_match,
    default_famous_catalog,
    load_famous_catalog,
)
from backend.modules.chess_intelligence.repository import ChessGameRepository

logger = logging.getLogger(__name__)


class FamousCatalogService:
    """Mark existing ``ChessGame`` rows famous from editorial YAML."""
    def __init__(
        self,
        db: AsyncSession,
        *,
        catalog: list[FamousGameEntry] | None = None,
    ) -> None:
        self.db = db
        self.repo = ChessGameRepository(db)
        self.catalog = catalog if catalog is not None else list(default_famous_catalog())

    async def apply_to_tenant(
        self,
        *,
        tenant_id: uuid.UUID,
        dry_run: bool = False,
        min_score: int = DEFAULT_MIN_SCORE,
        limit: int = 5000,
    ) -> FamousApplyReport:
        report = FamousApplyReport()
        games = await self.repo.list_for_tenant(tenant_id=tenant_id, limit=limit)
        for game in games:
            report.scanned += 1
            match = best_famous_match(game, self.catalog, min_score=min_score)
            if match is None:
                report.skipped_low_score += 1
                continue
            report.matched += 1
            report.matches.append((str(game.id), match.entry.title, match.score))
            if dry_run:
                continue
            if apply_famous_metadata(game, match.entry):
                report.updated += 1
        if not dry_run and report.updated:
            await self.db.flush()
        logger.info(
            "famous_catalog_apply tenant=%s scanned=%s matched=%s updated=%s dry_run=%s",
            tenant_id,
            report.scanned,
            report.matched,
            report.updated,
            dry_run,
        )
        return report


def reload_catalog(path: Path | None = None) -> list[FamousGameEntry]:
    """Load catalog bypassing process cache (tests / custom path)."""
    if path is not None:
        return load_famous_catalog(path)
    default_famous_catalog.cache_clear()
    return list(default_famous_catalog())

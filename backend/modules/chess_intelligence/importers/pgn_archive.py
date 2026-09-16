"""Streaming multi-game PGN archive import (no full-file load).

Historical games are durable local assets (see ``historical_assets``):

* Use this importer for ``HISTORICAL_BOOTSTRAP`` — do not add a parallel PGN importer.
* Idempotent: re-running the same archive identity yields zero new games/sources.
* Not scheduled daily; run on initial bootstrap or operator/version trigger only.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

import chess.pgn
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.dedupe import ChessGameDedupeService, SourceRef
from backend.modules.chess_intelligence.ingestion_mode import (
    ChessIngestionMode,
    stamp_ingestion_mode,
)
from backend.modules.chess_intelligence.licenses import license_for_provider
from backend.modules.chess_intelligence.normalizer import chess_game_from_parsed
from backend.modules.chess_intelligence.observability import record_game_import_progress
from backend.modules.chess_intelligence.operational_catalog import (
    SelectiveImportFilters,
    clamp_pgn_import_max_games,
    game_passes_selective_filters,
)
from backend.modules.chess_intelligence.source_rules import (
    ChessSourceRuleError,
    assert_bulk_file_allowed,
)
from backend.modules.chess_video.parser import ChessParseError, parse_chess_input

logger = logging.getLogger(__name__)

_MAX_ERROR_SAMPLES = 25


@dataclass
class ImportProgress:
    """Archive import counters — ``inserted``/``linked_source``/``skipped_duplicate``.

    Idempotent re-import of the same archive identity should look like::

        inserted=0, linked_source=0, skipped_duplicate=N
    """

    scanned: int = 0
    inserted: int = 0
    linked_source: int = 0
    skipped_duplicate: int = 0
    skipped_filtered: int = 0
    skipped_error: int = 0
    batches_committed: int = 0
    error_samples: list[str] = field(default_factory=list)

    def record_error(self, message: str) -> None:
        self.skipped_error += 1
        if len(self.error_samples) < _MAX_ERROR_SAMPLES:
            self.error_samples.append(message)

    @property
    def existing_or_duplicate(self) -> int:
        """Games already in catalog (linked or pure duplicate)."""
        return self.linked_source + self.skipped_duplicate


def iter_pgn_games(stream: TextIO) -> Iterator[tuple[int, str]]:
    """Yield (1-based index, single-game PGN text) without loading the whole file."""
    index = 0
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        index += 1
        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
        text = str(game.accept(exporter)).strip()
        if text:
            yield index, text + "\n"


def iter_pgn_file(path: Path) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        yield from iter_pgn_games(handle)


@dataclass
class PgnArchiveImportConfig:
    tenant_id: uuid.UUID
    file_path: Path
    provider: str = "pgn_archive"
    source_name: str = "archive"
    batch_size: int = 100
    dry_run: bool = False
    skip_games: int = 0
    max_games: int | None = None
    import_batch_id: str | None = None
    license_note: str | None = None
    # Historical archives default to bootstrap; keep override for rare re-runs.
    ingestion_mode: ChessIngestionMode = ChessIngestionMode.HISTORICAL_BOOTSTRAP
    # Optional reproducibility digest (from ``import_manifest.build_archive_manifest``).
    archive_sha256: str | None = None
    archive_bytes: int | None = None
    archive_uri: str | None = None
    archive_version: str | None = None
    # §18 selective import — shrink what enters Postgres; archive stays on disk.
    filters: SelectiveImportFilters = field(default_factory=SelectiveImportFilters)


class PgnArchiveImporter:
    """Stream a .pgn archive into ChessGame + ChessGameSource (fingerprint-deduped)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.dedupe = ChessGameDedupeService(db)

    async def run(
        self,
        config: PgnArchiveImportConfig,
        *,
        on_batch: Callable[[ImportProgress], Awaitable[None]] | None = None,
    ) -> ImportProgress:
        if config.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        try:
            provider = assert_bulk_file_allowed(config.provider)
        except ChessSourceRuleError as exc:
            raise ValueError(str(exc)) from exc
        batch_id = config.import_batch_id or str(uuid.uuid4())
        progress = ImportProgress()
        pending_since_commit = 0
        max_games = clamp_pgn_import_max_games(config.max_games)

        logger.info(
            "pgn_archive_import_start file=%s provider=%s source=%s dry_run=%s batch=%s max_games=%s",
            config.file_path,
            provider,
            config.source_name,
            config.dry_run,
            batch_id,
            max_games,
        )

        for game_index, pgn_text in iter_pgn_file(config.file_path):
            if game_index <= config.skip_games:
                continue
            if max_games is not None and progress.scanned >= max_games:
                break
            progress.scanned += 1
            try:
                parsed = parse_chess_input(pgn_text, "pgn")
            except ChessParseError as exc:
                progress.record_error(f"game {game_index}: {exc}")
                logger.warning("pgn_archive_parse_error index=%s error=%s", game_index, exc)
                continue
            if parsed.move_count < 1:
                progress.record_error(f"game {game_index}: no legal moves")
                continue

            meta = stamp_ingestion_mode(
                {
                    "source_name": config.source_name,
                    "archive_file": config.file_path.name,
                    "game_index": game_index,
                    "import_batch": batch_id,
                },
                config.ingestion_mode,
            )
            if config.archive_sha256:
                meta["archive_sha256"] = config.archive_sha256
            if config.archive_bytes is not None:
                meta["archive_bytes"] = config.archive_bytes
            if config.archive_uri:
                meta["archive_uri"] = config.archive_uri
            if config.archive_version:
                meta["archive_version"] = config.archive_version
            game = chess_game_from_parsed(
                tenant_id=config.tenant_id,
                parsed=parsed,
                source_provider=provider,
                source_metadata=meta,
            )
            if not game_passes_selective_filters(
                white_player=game.white_player,
                black_player=game.black_player,
                event=game.event,
                game_date=game.game_date,
                year=game.year,
                white_rating=game.white_rating,
                black_rating=game.black_rating,
                source_provider=provider,
                filters=config.filters,
            ):
                progress.skipped_filtered += 1
                continue
            source = SourceRef(
                provider=provider,
                source_name=config.source_name,
                source_metadata=meta,
                import_batch_id=batch_id,
                license_note=config.license_note or license_for_provider(provider),
                retrieved_at=datetime.now(timezone.utc),
            )

            if config.dry_run:
                existing = await self.dedupe.repo.get_by_fingerprint(
                    tenant_id=config.tenant_id,
                    game_fingerprint=game.game_fingerprint,
                )
                if existing is None:
                    progress.inserted += 1
                else:
                    # Would link or skip depending on source identity.
                    progress.linked_source += 1
                continue

            outcome = await self.dedupe.upsert_game(game=game, source=source)
            if outcome.created_game:
                progress.inserted += 1
            elif outcome.created_source:
                progress.linked_source += 1
            else:
                progress.skipped_duplicate += 1

            pending_since_commit += 1
            if pending_since_commit >= config.batch_size:
                await self.db.commit()
                progress.batches_committed += 1
                pending_since_commit = 0
                if on_batch is not None:
                    await on_batch(progress)

        if not config.dry_run and pending_since_commit:
            await self.db.commit()
            progress.batches_committed += 1
            if on_batch is not None:
                await on_batch(progress)

        logger.info(
            "pgn_archive_import_done scanned=%s inserted=%s linked=%s dupes=%s filtered=%s errors=%s commits=%s",
            progress.scanned,
            progress.inserted,
            progress.linked_source,
            progress.skipped_duplicate,
            progress.skipped_filtered,
            progress.skipped_error,
            progress.batches_committed,
        )
        record_game_import_progress(
            provider=provider,
            inserted=progress.inserted,
            linked=progress.linked_source,
            duplicates=progress.skipped_duplicate,
            invalid=progress.skipped_error,
            scanned=progress.scanned,
            dry_run=config.dry_run,
        )
        return progress

"""Streaming Lichess puzzle CSV / .csv.zst import (database.lichess.org/#puzzles).

FEN = before opponent move; Moves[0] = opponent; store player fen + Moves[1:].
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
import re
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, TextIO, cast

import chess
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.ingestion_mode import (
    ChessIngestionMode,
    stamp_ingestion_mode,
)
from backend.modules.chess_intelligence.models import ChessPuzzle
from backend.modules.chess_intelligence.normalizer import chess_puzzle_from_fields
from backend.modules.chess_intelligence.observability import record_puzzle_import_progress
from backend.modules.chess_intelligence.puzzle_catalog import (
    PuzzleImportFilters,
    clamp_puzzle_import_limit,
    puzzle_passes_filters,
)
from backend.modules.chess_intelligence.repository import ChessPuzzleRepository
from backend.modules.chess_intelligence.source_rules import (
    ChessSourceRuleError,
    assert_bulk_file_allowed,
)
from backend.modules.chess_video.parser import ChessParseError

logger = logging.getLogger(__name__)

PROVIDER_NAME = "lichess_puzzles"
_MAX_ERROR_SAMPLES = 25
_GAME_ID_RE = re.compile(r"lichess\.org/([a-zA-Z0-9]+)(?:/|$|\?)")


@dataclass
class PuzzleImportProgress:
    scanned: int = 0
    filtered: int = 0
    inserted: int = 0
    skipped_duplicate: int = 0
    skipped_error: int = 0
    batches_committed: int = 0
    error_samples: list[str] = field(default_factory=list)

    def record_error(self, message: str) -> None:
        self.skipped_error += 1
        if len(self.error_samples) < _MAX_ERROR_SAMPLES:
            self.error_samples.append(message)


@dataclass
class LichessPuzzleImportConfig:
    """Bulk puzzle dump → ``ChessPuzzle`` only (§19; never creates ChessGame rows)."""

    tenant_id: uuid.UUID
    file_path: Path
    batch_size: int = 200
    dry_run: bool = False
    limit: int | None = None
    min_rating: int | None = None
    max_rating: int | None = None
    min_popularity: int | None = None
    themes: list[str] = field(default_factory=list)  # AND
    openings: list[str] = field(default_factory=list)  # any-of
    daily_date_from: str | None = None
    daily_date_to: str | None = None
    providers: frozenset[str] | None = None
    import_batch_id: str | None = None
    license_note: str = "Lichess puzzle database — https://database.lichess.org/#puzzles"

    def selective_filters(self) -> PuzzleImportFilters:
        return PuzzleImportFilters(
            min_rating=self.min_rating,
            max_rating=self.max_rating,
            min_popularity=self.min_popularity,
            themes=tuple(self.themes),
            openings=tuple(self.openings),
            daily_date_from=self.daily_date_from,
            daily_date_to=self.daily_date_to,
            providers=self.providers,
        )


def _num(row: dict[str, str], name: str, as_type: type[int] | type[float]) -> int | float | None:
    raw = (row.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(float(raw)) if as_type is int else float(raw)
    except ValueError:
        return None


def row_to_player_puzzle(row: dict[str, str]) -> dict[str, Any]:
    """CSV row → fields for chess_puzzle_from_fields (python-chess validates)."""
    puzzle_id = (row.get("PuzzleId") or "").strip()
    fen_before = (row.get("FEN") or "").strip()
    moves_raw = (row.get("Moves") or "").strip()
    if not puzzle_id or not fen_before or not moves_raw:
        raise ChessParseError("missing PuzzleId, FEN, or Moves")
    moves = [m.lower() for m in moves_raw.split() if m.strip()]
    if len(moves) < 2:
        raise ChessParseError(f"puzzle {puzzle_id}: need opponent + ≥1 solution ply")
    try:
        board = chess.Board(fen_before)
    except ValueError as exc:
        raise ChessParseError(f"puzzle {puzzle_id}: bad FEN") from exc
    san_all: list[str] = []
    for ply, token in enumerate(moves, start=1):
        try:
            move = chess.Move.from_uci(token)
        except ValueError as exc:
            raise ChessParseError(f"puzzle {puzzle_id}: bad UCI ply {ply}: {token}") from exc
        if move not in board.legal_moves:
            raise ChessParseError(f"puzzle {puzzle_id}: illegal UCI ply {ply}: {token}")
        san_all.append(board.san(move))
        board.push(move)
    start = chess.Board(fen_before)
    start.push(chess.Move.from_uci(moves[0]))
    game_url = (row.get("GameUrl") or "").strip() or None
    match = _GAME_ID_RE.search(game_url) if game_url else None
    return {
        "external_id": puzzle_id,
        "starting_fen": start.fen(),
        "solution_moves_uci": moves[1:],
        "solution_moves_san": san_all[1:],
        "rating": _num(row, "Rating", int),
        "rating_deviation": _num(row, "RatingDeviation", float),
        "popularity": _num(row, "Popularity", int),
        "play_count": _num(row, "NbPlays", int),
        "themes": [t for t in (row.get("Themes") or "").split() if t],
        "opening_tags": [
            t for t in (row.get("OpeningTags") or "").replace(",", " ").split() if t
        ],
        "source_game_id": match.group(1) if match else None,
        "source_game_url": game_url,
        "source_metadata": {
            "dataset": "lichess_db_puzzle",
            "fen_before_opponent": fen_before,
            "opponent_move_uci": moves[0],
            "daily_date": (row.get("DailyDate") or "").strip() or None,
        },
    }


def _passes_filters(fields: dict[str, Any], config: LichessPuzzleImportConfig) -> bool:
    meta = fields.get("source_metadata") or {}
    return puzzle_passes_filters(
        rating=fields.get("rating") if isinstance(fields.get("rating"), int) else None,
        popularity=(
            fields.get("popularity") if isinstance(fields.get("popularity"), int) else None
        ),
        themes=list(fields.get("themes") or []),
        opening_tags=list(fields.get("opening_tags") or []),
        daily_date=meta.get("daily_date") if isinstance(meta, dict) else None,
        provider=PROVIDER_NAME,
        filters=config.selective_filters(),
    )


@contextmanager
def open_puzzle_csv(path: Path) -> Iterator[TextIO]:
    """Open plain CSV, .gz, or .zst without loading whole file."""
    name = path.name.lower()
    if name.endswith(".zst"):
        import zstandard as zstd

        raw = path.open("rb")
        reader = zstd.ZstdDecompressor().stream_reader(raw)
        text: TextIO = io.TextIOWrapper(reader, encoding="utf-8", newline="")
        try:
            yield text
        finally:
            text.close()
            reader.close()  # type: ignore[no-untyped-call]
            raw.close()
    elif name.endswith(".gz"):
        handle = cast(TextIO, gzip.open(path, "rt", encoding="utf-8", newline=""))
        try:
            yield handle
        finally:
            handle.close()
    else:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            yield handle


def iter_puzzle_csv_rows(stream: IO[str]) -> Iterator[dict[str, str]]:
    for row in csv.DictReader(stream):
        if row:
            yield {k: (v or "") for k, v in row.items() if k is not None}


class LichessPuzzleDatasetImporter:
    """Stream CSV → ChessPuzzle; idempotent on provider + external_id."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ChessPuzzleRepository(db)

    async def run(
        self,
        config: LichessPuzzleImportConfig,
        *,
        on_batch: Callable[[PuzzleImportProgress], Awaitable[None]] | None = None,
    ) -> PuzzleImportProgress:
        if config.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        try:
            assert_bulk_file_allowed(PROVIDER_NAME)
        except ChessSourceRuleError as exc:
            raise ValueError(str(exc)) from exc
        batch_id = config.import_batch_id or str(uuid.uuid4())
        progress = PuzzleImportProgress()
        pending: list[ChessPuzzle] = []
        pending_ids: list[str] = []
        selected = 0
        seen: set[str] = set()
        limit = clamp_puzzle_import_limit(config.limit)
        logger.info(
            "lichess_puzzle_import_start file=%s dry_run=%s limit=%s",
            config.file_path,
            config.dry_run,
            limit,
        )
        with open_puzzle_csv(config.file_path) as stream:
            for row in iter_puzzle_csv_rows(stream):
                if limit is not None and selected >= limit:
                    break
                progress.scanned += 1
                try:
                    fields = row_to_player_puzzle(row)
                except ChessParseError as exc:
                    progress.record_error(str(exc))
                    continue
                except Exception as exc:  # noqa: BLE001
                    progress.record_error(f"row error: {exc}")
                    continue
                if not _passes_filters(fields, config):
                    progress.filtered += 1
                    continue
                ext_id = str(fields["external_id"])
                if ext_id in seen:
                    progress.skipped_duplicate += 1
                    selected += 1
                    continue
                seen.add(ext_id)
                selected += 1
                meta = stamp_ingestion_mode(
                    {
                        **dict(fields["source_metadata"]),
                        "import_batch": batch_id,
                        "license": config.license_note,
                    },
                    ChessIngestionMode.PUZZLE_SYNC,
                )
                pending.append(
                    chess_puzzle_from_fields(
                        tenant_id=config.tenant_id,
                        external_id=ext_id,
                        provider=PROVIDER_NAME,
                        starting_fen=fields["starting_fen"],
                        solution_moves_uci=fields["solution_moves_uci"],
                        solution_moves_san=fields["solution_moves_san"],
                        rating=fields.get("rating"),
                        rating_deviation=fields.get("rating_deviation"),
                        popularity=fields.get("popularity"),
                        play_count=fields.get("play_count"),
                        themes=fields.get("themes"),
                        opening_tags=fields.get("opening_tags"),
                        source_game_id=fields.get("source_game_id"),
                        source_game_url=fields.get("source_game_url"),
                        source_metadata=meta,
                        retrieved_at=datetime.now(timezone.utc),
                        import_batch_id=batch_id,
                        license_note=config.license_note,
                    )
                )
                pending_ids.append(ext_id)
                if len(pending) >= config.batch_size:
                    await self._flush(config, progress, pending, pending_ids)
                    pending, pending_ids = [], []
                    if on_batch is not None:
                        await on_batch(progress)
        if pending:
            await self._flush(config, progress, pending, pending_ids)
            if on_batch is not None:
                await on_batch(progress)
        logger.info(
            "lichess_puzzle_import_done scanned=%s inserted=%s dupes=%s errors=%s",
            progress.scanned,
            progress.inserted,
            progress.skipped_duplicate,
            progress.skipped_error,
        )
        record_puzzle_import_progress(
            provider=PROVIDER_NAME,
            inserted=progress.inserted,
            duplicates=progress.skipped_duplicate,
            invalid=progress.skipped_error,
            filtered=progress.filtered,
            scanned=progress.scanned,
            dry_run=config.dry_run,
        )
        return progress

    async def _flush(
        self,
        config: LichessPuzzleImportConfig,
        progress: PuzzleImportProgress,
        pending: list[ChessPuzzle],
        pending_ids: list[str],
    ) -> None:
        existing = await self.repo.existing_external_ids(
            tenant_id=config.tenant_id,
            provider=PROVIDER_NAME,
            external_ids=pending_ids,
        )
        to_insert = [p for p in pending if p.external_id not in existing]
        progress.skipped_duplicate += len(pending) - len(to_insert)
        if not to_insert:
            return
        if config.dry_run:
            progress.inserted += len(to_insert)
            return
        await self.repo.add_many(to_insert)
        await self.db.commit()
        progress.inserted += len(to_insert)
        progress.batches_committed += 1

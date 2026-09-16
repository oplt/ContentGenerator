#!/usr/bin/env python3
"""Import Lichess puzzle CSV / .csv.zst into chess_puzzles (streaming).

Download externally from https://database.lichess.org/#puzzles — do not commit
the multi-million-row dump into git.

Example:

  cd backend && PYTHONPATH=.. .venv/bin/python -m backend.scripts.import_lichess_puzzles \\
    --file /data/lichess_db_puzzle.csv.zst \\
    --tenant-id 00000000-0000-4000-8000-000000000001 \\
    --limit 10000 --min-rating 1200 --max-rating 2000 \\
    --themes mate fork --min-popularity 50 --batch-size 200
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

from backend.db.session import SessionLocal
from backend.modules.chess_intelligence.importers import (
    LichessPuzzleDatasetImporter,
    LichessPuzzleImportConfig,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stream-import Lichess puzzle dataset")
    p.add_argument("--file", required=True, type=Path, help="Path to .csv / .csv.gz / .csv.zst")
    p.add_argument("--tenant-id", required=True, type=uuid.UUID)
    p.add_argument("--limit", type=int, default=None, help="Max puzzles after filters")
    p.add_argument("--min-rating", type=int, default=None)
    p.add_argument("--max-rating", type=int, default=None)
    p.add_argument("--min-popularity", type=int, default=None)
    p.add_argument(
        "--themes",
        nargs="*",
        default=[],
        help="Require all listed themes (AND)",
    )
    p.add_argument("--batch-size", type=int, default=200)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--import-batch-id", default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    path: Path = args.file
    if not path.is_file():
        logging.error("file not found: %s", path)
        return 2
    config = LichessPuzzleImportConfig(
        tenant_id=args.tenant_id,
        file_path=path.resolve(),
        batch_size=max(int(args.batch_size), 1),
        dry_run=bool(args.dry_run),
        limit=args.limit,
        min_rating=args.min_rating,
        max_rating=args.max_rating,
        min_popularity=args.min_popularity,
        themes=list(args.themes or []),
        import_batch_id=args.import_batch_id,
    )
    async with SessionLocal() as db:
        progress = await LichessPuzzleDatasetImporter(db).run(config)
    print(
        "import complete "
        f"scanned={progress.scanned} filtered={progress.filtered} "
        f"inserted={progress.inserted} duplicates={progress.skipped_duplicate} "
        f"errors={progress.skipped_error} commits={progress.batches_committed} "
        f"dry_run={config.dry_run}"
    )
    if progress.error_samples:
        print("error samples:")
        for sample in progress.error_samples:
            print(f"  - {sample}")
    return 0 if progress.skipped_error == 0 or progress.inserted > 0 else 1


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main(sys.argv[1:])

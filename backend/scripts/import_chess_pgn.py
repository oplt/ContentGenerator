#!/usr/bin/env python3
"""Import a multi-game PGN archive into the chess_games catalog.

Example:

  cd backend && PYTHONPATH=.. .venv/bin/python -m backend.scripts.import_chess_pgn \\
    --file /data/wch.pgn \\
    --tenant-id 00000000-0000-4000-8000-000000000001 \\
    --provider pgn_mentor \\
    --source-name world_championship \\
    --batch-size 100
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
    PgnArchiveImportConfig,
    PgnArchiveImporter,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream-import a PGN archive into chess_games")
    parser.add_argument("--file", required=True, type=Path, help="Path to .pgn archive")
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID, help="Target tenant UUID")
    parser.add_argument(
        "--provider",
        default="pgn_archive",
        help="source_provider label (e.g. pgn_mentor, archive)",
    )
    parser.add_argument(
        "--source-name",
        default="archive",
        help="Collection / archive name stored in source_metadata",
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Commit every N new games")
    parser.add_argument("--dry-run", action="store_true", help="Parse + dedupe; no DB writes")
    parser.add_argument(
        "--skip-games",
        type=int,
        default=0,
        help="Skip first N games in file (resume aid)",
    )
    parser.add_argument("--max-games", type=int, default=None, help="Stop after N scanned games")
    parser.add_argument(
        "--import-batch-id",
        default=None,
        help="Stable batch id for provenance (default: random UUID)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    path: Path = args.file
    if not path.is_file():
        logging.error("file not found: %s", path)
        return 2

    config = PgnArchiveImportConfig(
        tenant_id=args.tenant_id,
        file_path=path.resolve(),
        provider=args.provider.strip() or "pgn_archive",
        source_name=args.source_name.strip() or "archive",
        batch_size=max(int(args.batch_size), 1),
        dry_run=bool(args.dry_run),
        skip_games=max(int(args.skip_games), 0),
        max_games=args.max_games,
        import_batch_id=args.import_batch_id,
    )

    async with SessionLocal() as db:
        progress = await PgnArchiveImporter(db).run(config)

    print(
        "import complete "
        f"scanned={progress.scanned} inserted={progress.inserted} "
        f"linked_source={progress.linked_source} "
        f"duplicates={progress.skipped_duplicate} errors={progress.skipped_error} "
        f"commits={progress.batches_committed} dry_run={config.dry_run}"
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

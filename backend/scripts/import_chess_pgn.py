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
from backend.modules.chess_intelligence.import_manifest import build_archive_manifest
from backend.modules.chess_intelligence.operational_catalog import filters_from_params


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
    parser.add_argument("--year-from", type=int, default=None, help="Keep games with year >= N")
    parser.add_argument("--year-to", type=int, default=None, help="Keep games with year <= N")
    parser.add_argument("--player", default=None, help="White or black name contains")
    parser.add_argument("--white", default=None, help="White player name contains")
    parser.add_argument("--black", default=None, help="Black player name contains")
    parser.add_argument("--event", default=None, help="Event name contains")
    parser.add_argument(
        "--min-rating",
        type=int,
        default=None,
        help="Require either side rating >= N when ratings present",
    )
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

    resolved = path.resolve()
    manifest = build_archive_manifest(
        path=resolved,
        provider=args.provider.strip() or "pgn_archive",
        source_name=args.source_name.strip() or "archive",
        import_batch_id=args.import_batch_id,
    )

    config = PgnArchiveImportConfig(
        tenant_id=args.tenant_id,
        file_path=resolved,
        provider=args.provider.strip() or "pgn_archive",
        source_name=args.source_name.strip() or "archive",
        batch_size=max(int(args.batch_size), 1),
        dry_run=bool(args.dry_run),
        skip_games=max(int(args.skip_games), 0),
        max_games=args.max_games,
        import_batch_id=args.import_batch_id,
        archive_sha256=manifest.checksum_sha256,
        archive_bytes=manifest.size_bytes,
        archive_uri=manifest.source_uri,
        filters=filters_from_params(
            {
                "year_from": args.year_from,
                "year_to": args.year_to,
                "player": args.player,
                "white": args.white,
                "black": args.black,
                "event": args.event,
                "min_rating": args.min_rating,
            }
        ),
    )

    async with SessionLocal() as db:
        progress = await PgnArchiveImporter(db).run(config)

    print(
        "import complete "
        f"scanned={progress.scanned} inserted={progress.inserted} "
        f"linked_source={progress.linked_source} "
        f"duplicates={progress.skipped_duplicate} "
        f"filtered={progress.skipped_filtered} errors={progress.skipped_error} "
        f"commits={progress.batches_committed} dry_run={config.dry_run} "
        f"sha256={manifest.checksum_sha256} bytes={manifest.size_bytes}"
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

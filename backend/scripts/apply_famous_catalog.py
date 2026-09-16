#!/usr/bin/env python3
"""Match curated famous-game catalog onto chess_games for a tenant.

Example:

  cd backend && PYTHONPATH=.. .venv/bin/python -m backend.scripts.apply_famous_catalog \\
    --tenant-id 00000000-0000-4000-8000-000000000001 \\
    --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

from backend.db.session import SessionLocal
from backend.modules.chess_intelligence.famous_catalog import load_famous_catalog
from backend.modules.chess_intelligence.famous_service import FamousCatalogService


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply famous-game catalog to chess_games")
    parser.add_argument("--tenant-id", required=True, type=uuid.UUID)
    parser.add_argument("--catalog", type=Path, default=None, help="Override YAML path")
    parser.add_argument("--min-score", type=int, default=70)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    catalog = load_famous_catalog(args.catalog) if args.catalog else None
    async with SessionLocal() as db:
        report = await FamousCatalogService(db, catalog=catalog).apply_to_tenant(
            tenant_id=args.tenant_id,
            dry_run=bool(args.dry_run),
            min_score=int(args.min_score),
            limit=int(args.limit),
        )
        if not args.dry_run:
            await db.commit()
    print(
        "famous catalog apply "
        f"scanned={report.scanned} matched={report.matched} "
        f"updated={report.updated} skipped={report.skipped_low_score} "
        f"dry_run={args.dry_run}"
    )
    for game_id, title, score in report.matches[:20]:
        print(f"  - {title} score={score} game={game_id}")
    if len(report.matches) > 20:
        print(f"  … {len(report.matches) - 20} more")
    return 0


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main(sys.argv[1:])

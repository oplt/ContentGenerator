"""Famous games = editorial classification on canonical ChessGame (not a second PGN copy).

Lifecycle::

    canonical ChessGame
            ↓
    famous YAML / editorial metadata (``FamousCatalogService``)
            ↓
    historical/famous presentation (``is_famous``, title, tags)

Rules:

* Do **not** introduce a ``FamousGame`` / ``ChessFamousGame`` SQL table unless product
  needs multiple catalogs, versioned curation, brand-specific sets, or editorial history.
* ``enrich_famous`` / ``apply_famous_catalog`` only mutate metadata on existing rows.
* Never schedule redownload of famous historical PGNs (see ``historical_assets`` beat ban).
* Fame ≠ recent/notable ≠ content-opportunity score (those are separate concepts).
"""

from __future__ import annotations

from pathlib import Path

# ORM class names that must not appear — fame lives on ChessGame columns.
FORBIDDEN_FAMOUS_ORM_NAMES: frozenset[str] = frozenset(
    {
        "FamousGame",
        "ChessFamousGame",
        "FamousHistoricalGame",
        "DownloadedFamousGame",
    }
)

# Provider modules that famous curation must never import/call.
FORBIDDEN_FAMOUS_PROVIDER_IMPORTS: frozenset[str] = frozenset(
    {
        "LichessMastersProvider",
        "ChessComProvider",
        "LichessPuzzlesProvider",
        "normalize_external_game",
        "provider_sync",
    }
)

FAMOUS_CURATION_PATHS: tuple[str, ...] = (
    "famous_catalog.py",
    "famous_service.py",
    "catalog_job_runners.py",  # _enrich_famous only
)


def famous_curation_is_metadata_only() -> bool:
    """Policy flag for docs/tests — enrichment does not fetch PGN."""
    return True


def scan_famous_modules_for_provider_calls(module_root: Path) -> list[str]:
    """Return file:token hits if famous curation modules reference live providers."""
    hits: list[str] = []
    for rel in ("famous_catalog.py", "famous_service.py", "data/famous_games.yaml"):
        path = module_root / rel
        if not path.is_file():
            continue
        if path.suffix == ".yaml":
            continue
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_FAMOUS_PROVIDER_IMPORTS:
            if token in text:
                hits.append(f"{rel}:{token}")
    # Enrich runner may live beside other kinds — only flag provider use inside _enrich_famous.
    runners = module_root / "catalog_job_runners.py"
    if runners.is_file():
        text = runners.read_text(encoding="utf-8")
        # Slice from _enrich_famous to EOF (last kind handler).
        marker = "async def _enrich_famous"
        if marker in text:
            chunk = text.split(marker, 1)[1]
            for token in FORBIDDEN_FAMOUS_PROVIDER_IMPORTS:
                if token in chunk:
                    hits.append(f"catalog_job_runners.py:_enrich_famous:{token}")
    return hits

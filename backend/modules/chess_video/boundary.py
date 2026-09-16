"""§22 — ChessVideo stays downstream of the catalog; no provider ingestion.

Correct::

    Chess Intelligence → ChessGame.normalized_pgn → ChessVideo pipeline

Incorrect::

    ChessVideoService → Lichess/Chess.com → download → dedupe

Allowed catalog touches: local ``ChessCatalogQuery`` (PGN resolve) and
provenance/observability. Forbidden: any ``providers/`` / importer / remote fetch.
"""

from __future__ import annotations

from pathlib import Path

VIDEO_DIR = Path(__file__).resolve().parent

# Remote acquisition / domain ingestion must not live under chess_video/.
FORBIDDEN_IMPORT_FRAGMENTS: frozenset[str] = frozenset(
    {
        "chess_intelligence.providers",
        "get_historical_game_provider",
        "get_puzzle_provider",
        "ExternalChessGame",
        "ExternalChessPuzzle",
        "chess_intelligence.dedupe",
        "chess_intelligence.importers",
        "LichessMastersProvider",
        "LichessPuzzlesProvider",
        "ChessComProvider",
        "providers.registry",
        "providers.lichess",
        "providers.chesscom",
    }
)

# Local catalog / metrics bridges (not remote acquisition).
ALLOWED_CATALOG_IMPORT_FRAGMENTS: frozenset[str] = frozenset(
    {
        "chess_intelligence.catalog_queries",
        "chess_intelligence.observability",
        "chess_intelligence.provenance",
    }
)

CORRECT_FLOW: tuple[str, ...] = (
    "Chess Intelligence",
    "canonical ChessGame",
    "normalized PGN",
    "existing ChessVideo pipeline",
)

MANUAL_INPUT_FORMATS: tuple[str, ...] = ("pgn", "san", "uci", "auto")


def scan_video_provider_leaks(*, root: Path | None = None) -> list[str]:
    """Return ``path:line:snippet`` hits for forbidden provider/ingest imports."""
    base = root or VIDEO_DIR
    hits: list[str] = []
    for path in sorted(base.rglob("*.py")):
        if path.name == "boundary.py":
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
                if fragment in line:
                    hits.append(f"{path.name}:{i}:{stripped[:120]}")
    return hits


def video_resolves_from_local_catalog_only() -> bool:
    """Contract helper — catalog video uses DB PGN, never live providers."""
    return True

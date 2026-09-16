"""Known data-source / license notes for chess providers (Phase 19)."""

from __future__ import annotations

# Curated, stable strings — never invent license claims beyond documented sources.
PROVIDER_LICENSE_NOTES: dict[str, str] = {
    "lichess_masters": (
        "Lichess Opening Explorer masters games — "
        "https://lichess.org/api#tag/Opening-Explorer"
    ),
    "lichess_puzzles": (
        "Lichess puzzle database / API — https://database.lichess.org/#puzzles"
    ),
    "lichess": (
        "Lichess public API — https://lichess.org/api"
    ),
    "chesscom": (
        "Chess.com Published Data API — "
        "https://www.chess.com/news/view/published-data-api"
    ),
    "pgn_archive": (
        "PGN archive import — license depends on the archive operator; "
        "see import batch source_metadata"
    ),
    "pgn_mentor": (
        "PGN Mentor / archive import — license depends on the archive operator; "
        "see import batch source_metadata"
    ),
    "manual": "Manually imported PGN (operator-supplied)",
    "api_import": "Imported via SignalForge chess catalog API",
    "famous_catalog": "Editorial famous-game catalog association (local curation)",
}


def license_for_provider(provider: str | None) -> str | None:
    if not provider:
        return None
    return PROVIDER_LICENSE_NOTES.get(provider.strip().lower())

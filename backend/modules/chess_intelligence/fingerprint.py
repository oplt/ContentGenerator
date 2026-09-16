"""Deterministic chess game / puzzle fingerprints for deduplication (§17).

Canonical game identity is *chess* information only::

    sha256(starting_fen | " ".join(uci_moves) | result)

Harmless PGN differences (comments, formatting, header order, NAGs/annotations)
must not change the fingerprint after parse. Provider external IDs are provenance,
never part of the fingerprint — do not treat them as canonical game IDs.

All catalog ingress converges on::

    normalize → fingerprint → ChessGameDedupeService

Providers must not implement their own dedupe layer.
"""

from __future__ import annotations

import hashlib
import re

from backend.modules.chess_video.parser import ParsedChessGame

# Fingerprint = starting_fen | uci_moves | result.
# Player names / event / date / provider ids intentionally excluded.


def compute_game_fingerprint(
    *,
    starting_fen: str,
    uci_moves: list[str],
    result: str | None,
) -> str:
    """Identity hash: starting FEN + UCI sequence + result (not provider IDs)."""
    moves = " ".join(m.strip().lower() for m in uci_moves if m and m.strip())
    payload = f"{starting_fen.strip()}|{moves}|{(result or '*').strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint_from_parsed(parsed: ParsedChessGame) -> str:
    return compute_game_fingerprint(
        starting_fen=parsed.starting_fen,
        uci_moves=parsed.uci_moves,
        result=parsed.result,
    )


def compute_content_hash(normalized_pgn: str) -> str:
    """Hash of canonical PGN text (detect re-exports / whitespace-normalized dupes)."""
    return hashlib.sha256(normalized_pgn.strip().encode("utf-8")).hexdigest()


def compute_puzzle_fingerprint(
    *,
    starting_fen: str,
    solution_moves_uci: list[str],
) -> str:
    moves = " ".join(m.strip().lower() for m in solution_moves_uci if m and m.strip())
    payload = f"{starting_fen.strip()}|{moves}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_PLAYER_NOISE = re.compile(r"[^a-z0-9]+")


def normalize_player_name(name: str | None) -> str:
    """Lowercase alphanumeric collapse — for catalog matching, not fingerprinting."""
    if not name:
        return ""
    return _PLAYER_NOISE.sub(" ", name.lower()).strip()

"""Editorial famous-game catalog: load YAML, score matches, apply metadata.

Phase 20: SignalForge-owned editorial metadata only. Do not scrape proprietary
annotations/comments from chessgames.com or similar curated sites.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from backend.modules.chess_intelligence.fingerprint import normalize_player_name
from backend.modules.chess_intelligence.models import ChessGame
from backend.modules.chess_video.parser import ChessParseError, parse_chess_input

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "famous_games.yaml"
DEFAULT_MIN_SCORE = 70


class FamousGameEntry(BaseModel):
    id: str
    title: str
    white: str
    black: str
    year: int
    aliases: list[str] = Field(default_factory=list)
    white_aliases: list[str] = Field(default_factory=list)
    black_aliases: list[str] = Field(default_factory=list)
    event: str | None = None
    event_aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    historical_significance: str = ""
    uci_prefix: str | None = None
    game_fingerprint: str | None = None

    @field_validator("uci_prefix", mode="before")
    @classmethod
    def _norm_uci_prefix(cls, value: object) -> object:
        if isinstance(value, str):
            tokens = [t.lower() for t in value.replace(",", " ").split() if t]
            return " ".join(tokens) or None
        return value


@dataclass
class FamousMatch:
    entry: FamousGameEntry
    score: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class FamousApplyReport:
    scanned: int = 0
    matched: int = 0
    updated: int = 0
    skipped_low_score: int = 0
    matches: list[tuple[str, str, int]] = field(default_factory=list)  # game_id, title, score


def load_famous_catalog(path: Path | None = None) -> list[FamousGameEntry]:
    catalog_path = path or DEFAULT_CATALOG_PATH
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("games"), list):
        raise ValueError(f"Invalid famous catalog format: {catalog_path}")
    return [FamousGameEntry.model_validate(item) for item in raw["games"]]


@lru_cache(maxsize=1)
def default_famous_catalog() -> tuple[FamousGameEntry, ...]:
    return tuple(load_famous_catalog())


def _name_candidates(primary: str, aliases: list[str]) -> list[str]:
    out = [normalize_player_name(primary)]
    out.extend(normalize_player_name(a) for a in aliases)
    return [n for n in out if n]


def _player_match(primary: str, aliases: list[str], actual: str | None) -> bool:
    actual_n = normalize_player_name(actual)
    if not actual_n:
        return False
    for candidate in _name_candidates(primary, aliases):
        if candidate in actual_n or actual_n in candidate:
            return True
        # Token overlap (e.g. "fischer" in "robert james fischer")
        cand_tokens = set(candidate.split())
        actual_tokens = set(actual_n.split())
        if cand_tokens and cand_tokens <= actual_tokens:
            return True
        if len(cand_tokens & actual_tokens) >= 1 and max(len(t) for t in cand_tokens) >= 4:
            if cand_tokens & actual_tokens:
                # Prefer surname-length tokens
                if any(len(t) >= 4 and t in actual_tokens for t in cand_tokens):
                    return True
    return False


def _event_match(entry: FamousGameEntry, event: str | None) -> bool:
    actual = normalize_player_name(event)  # same alnum collapse
    if not actual:
        return False
    candidates = [normalize_player_name(entry.event)] if entry.event else []
    candidates.extend(normalize_player_name(a) for a in entry.event_aliases)
    for candidate in candidates:
        if not candidate:
            continue
        if candidate in actual or actual in candidate:
            return True
        if set(candidate.split()) & set(actual.split()):
            return True
    return False


def _uci_list(game: ChessGame) -> list[str]:
    try:
        parsed = parse_chess_input(game.normalized_pgn, "pgn")
    except ChessParseError:
        return []
    return list(parsed.uci_moves)


def _uci_prefix_match(uci_moves: list[str], prefix: str) -> bool:
    want = [t for t in prefix.split() if t]
    if not want or len(uci_moves) < len(want):
        return False
    have = [m.lower() for m in uci_moves[: len(want)]]
    return have == want


def score_famous_match(
    entry: FamousGameEntry,
    game: ChessGame,
    *,
    uci_moves: list[str] | None = None,
) -> FamousMatch | None:
    """Multi-signal score. Year is required when entry has year; names alone never enough."""
    reasons: list[str] = []
    score = 0
    moves = uci_moves if uci_moves is not None else _uci_list(game)

    if entry.game_fingerprint and game.game_fingerprint == entry.game_fingerprint:
        return FamousMatch(entry=entry, score=100, reasons=["exact_fingerprint"])

    if entry.year:
        if game.year == entry.year:
            score += 40
            reasons.append("year")
        elif game.year is not None and abs(game.year - entry.year) <= 1:
            score += 15
            reasons.append("year_near")
        else:
            return None

    if entry.uci_prefix and _uci_prefix_match(moves, entry.uci_prefix):
        score += 50
        reasons.append("uci_prefix")

    white_ok = _player_match(entry.white, entry.white_aliases, game.white_player)
    black_ok = _player_match(entry.black, entry.black_aliases, game.black_player)
    if white_ok:
        score += 25
        reasons.append("white")
    if black_ok:
        score += 25
        reasons.append("black")

    if _event_match(entry, game.event):
        score += 10
        reasons.append("event")

    # Reject weak combinations (names alone never enough; need year+both or moves).
    if score < DEFAULT_MIN_SCORE:
        return None
    strong_moves = "uci_prefix" in reasons or "exact_fingerprint" in reasons
    both_and_year = white_ok and black_ok and "year" in reasons
    if not strong_moves and not both_and_year:
        return None

    return FamousMatch(entry=entry, score=score, reasons=reasons)


def best_famous_match(
    game: ChessGame,
    catalog: list[FamousGameEntry] | tuple[FamousGameEntry, ...] | None = None,
    *,
    min_score: int = DEFAULT_MIN_SCORE,
) -> FamousMatch | None:
    entries = list(catalog) if catalog is not None else list(default_famous_catalog())
    uci_moves = _uci_list(game)
    best: FamousMatch | None = None
    for entry in entries:
        match = score_famous_match(entry, game, uci_moves=uci_moves)
        if match is None or match.score < min_score:
            continue
        if best is None or match.score > best.score:
            best = match
    return best


def apply_famous_metadata(game: ChessGame, entry: FamousGameEntry) -> bool:
    """Mutate game with curated famous fields. Returns True if anything changed."""
    changed = False
    if not game.is_famous:
        game.is_famous = True
        changed = True
    if game.famous_title != entry.title:
        game.famous_title = entry.title
        changed = True
    tags = list(game.historical_tags or [])
    desired = list(entry.tags)
    if "famous" not in desired:
        desired.append("famous")
    catalog_tag = f"catalog:{entry.id}"
    if catalog_tag not in desired:
        desired.append(catalog_tag)
    merged = list(dict.fromkeys([*tags, *desired]))
    if merged != tags:
        game.historical_tags = merged
        changed = True
    if entry.event and not game.event:
        game.event = entry.event
        changed = True
    if entry.year and game.year is None:
        game.year = entry.year
        changed = True
    # Keep a short editorial note in source_metadata without clobbering provenance.
    meta = dict(game.source_metadata or {})
    if meta.get("famous_catalog_id") != entry.id:
        meta["famous_catalog_id"] = entry.id
        if entry.historical_significance:
            meta["famous_significance"] = entry.historical_significance.strip()
        game.source_metadata = meta
        changed = True
    return changed

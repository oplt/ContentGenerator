"""Transparent content-opportunity score from explicit catalog + analysis signals.

No LLM / opaque model. Caps are documented; components always sum to ``score``.

This is the **content opportunity** concept only (§8). It may *use* ``is_famous`` as
one input component, but it is not a synonym for famous or recent/notable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

# Component ceilings (sum = 100).
CAP_HISTORICAL = 20
CAP_PLAYER_FAME = 10
CAP_TACTICAL = 18
CAP_EVAL_SWING = 16
CAP_PUZZLE = 15
CAP_VIDEO = 15
CAP_DATE = 6

COMPONENT_CAPS: dict[str, int] = {
    "historical_significance": CAP_HISTORICAL,
    "player_fame": CAP_PLAYER_FAME,
    "tactical_intensity": CAP_TACTICAL,
    "evaluation_swing": CAP_EVAL_SWING,
    "puzzle_suitability": CAP_PUZZLE,
    "video_suitability": CAP_VIDEO,
    "date_relevance": CAP_DATE,
}


@dataclass(slots=True, frozen=True)
class ContentOpportunityResult:
    score: int
    components: dict[str, int]
    reasons: dict[str, list[str]]
    formula_version: str = "content_opportunity_v1"


def _clamp(value: int, cap: int) -> int:
    return max(0, min(cap, value))


def _month_day(game_date: str | None) -> tuple[int, int] | None:
    if not game_date:
        return None
    # Accept YYYY.MM.DD / YYYY-MM-DD
    cleaned = game_date.strip().replace("-", ".")
    parts = cleaned.split(".")
    if len(parts) < 3:
        return None
    try:
        month, day = int(parts[1]), int(parts[2])
        if 1 <= month <= 12 and 1 <= day <= 31:
            return month, day
    except ValueError:
        return None
    return None


def compute_content_opportunity(
    *,
    is_famous: bool = False,
    famous_title: str | None = None,
    historical_tags: Sequence[str] | None = None,
    white_rating: int | None = None,
    black_rating: int | None = None,
    opening: str | None = None,
    eco: str | None = None,
    move_count: int = 0,
    game_date: str | None = None,
    moment_classifications: Sequence[str] | None = None,
    tactical_patterns: Sequence[str] | None = None,
    today: date | None = None,
) -> ContentOpportunityResult:
    """Score a game for content worthiness from explicit inputs only."""
    tags = list(historical_tags or [])
    moments = list(moment_classifications or [])
    patterns = list(tactical_patterns or [])
    reasons: dict[str, list[str]] = {key: [] for key in COMPONENT_CAPS}

    # --- historical_significance (0-20) ---
    hist = 0
    if is_famous:
        hist += 14
        reasons["historical_significance"].append("is_famous")
    if famous_title:
        hist += 4
        reasons["historical_significance"].append("famous_title")
    if tags:
        hist += min(4, len(tags) * 2)
        reasons["historical_significance"].append(f"tags:{len(tags)}")
    hist = _clamp(hist, CAP_HISTORICAL)

    # --- player_fame (0-10) from ratings only (transparent) ---
    fame = 0
    for label, rating in (("white", white_rating), ("black", black_rating)):
        if rating is None:
            continue
        if rating >= 2700:
            fame += 5
            reasons["player_fame"].append(f"{label}_rating>={rating}")
        elif rating >= 2500:
            fame += 3
            reasons["player_fame"].append(f"{label}_rating>={rating}")
        elif rating >= 2300:
            fame += 1
            reasons["player_fame"].append(f"{label}_rating>={rating}")
    fame = _clamp(fame, CAP_PLAYER_FAME)

    # --- tactical_intensity (0-18) ---
    tac = 0
    pattern_bonus = {
        "fork": 3,
        "pin": 2,
        "skewer": 3,
        "discovered_attack": 3,
        "double_attack": 3,
        "back_rank_mate": 5,
        "smothered_mate": 5,
        "queen_sacrifice": 4,
        "rook_sacrifice": 3,
        "exchange_sacrifice": 3,
        "bishop_sacrifice": 2,
        "knight_sacrifice": 2,
        "promotion": 2,
        "underpromotion": 3,
    }
    for pattern in patterns:
        add = pattern_bonus.get(pattern, 1)
        tac += add
        reasons["tactical_intensity"].append(f"{pattern}+{add}")
    for label in ("blunder", "mistake", "missed_win"):
        n = moments.count(label)
        if n:
            add = min(6, n * 2)
            tac += add
            reasons["tactical_intensity"].append(f"{label}x{n}+{add}")
    tac = _clamp(tac, CAP_TACTICAL)

    # --- evaluation_swing (0-16) ---
    swing = 0
    for label, weight in (
        ("large_evaluation_swing", 4),
        ("turning_point", 4),
        ("forced_mate", 5),
        ("mate_threat", 3),
        ("sacrifice", 3),
    ):
        n = moments.count(label)
        if n:
            add = min(12, n * weight)
            swing += add
            reasons["evaluation_swing"].append(f"{label}x{n}+{add}")
    swing = _clamp(swing, CAP_EVAL_SWING)

    # --- puzzle_suitability (0-15): short sharp tactics ---
    puzzle = 0
    sharp = sum(
        1
        for p in patterns
        if p in {"fork", "pin", "skewer", "discovered_attack", "double_attack", "smothered_mate"}
    )
    if sharp:
        puzzle += min(8, sharp * 2)
        reasons["puzzle_suitability"].append(f"sharp_patterns:{sharp}")
    if "forced_mate" in moments or "back_rank_mate" in patterns or "smothered_mate" in patterns:
        puzzle += 4
        reasons["puzzle_suitability"].append("mate_motif")
    if 4 <= move_count <= 40:
        puzzle += 3
        reasons["puzzle_suitability"].append("short_game_length")
    elif move_count <= 60:
        puzzle += 1
        reasons["puzzle_suitability"].append("moderate_length")
    puzzle = _clamp(puzzle, CAP_PUZZLE)

    # --- video_suitability (0-15) ---
    video = 0
    if 12 <= move_count <= 80:
        video += 8
        reasons["video_suitability"].append("move_count_in_band")
    elif 8 <= move_count <= 120:
        video += 4
        reasons["video_suitability"].append("move_count_ok")
    if is_famous or famous_title:
        video += 4
        reasons["video_suitability"].append("famous_hook")
    if opening or eco:
        video += 2
        reasons["video_suitability"].append("opening_label")
    if moments or patterns:
        video += 3
        reasons["video_suitability"].append("has_highlights")
    video = _clamp(video, CAP_VIDEO)

    # --- date_relevance (0-6): anniversary of game_date ---
    date_pts = 0
    md = _month_day(game_date)
    ref = today or date.today()
    if md and md == (ref.month, ref.day):
        date_pts = 6
        reasons["date_relevance"].append("anniversary_today")
    elif md and md[0] == ref.month:
        date_pts = 2
        reasons["date_relevance"].append("anniversary_month")
    date_pts = _clamp(date_pts, CAP_DATE)

    components = {
        "historical_significance": hist,
        "player_fame": fame,
        "tactical_intensity": tac,
        "evaluation_swing": swing,
        "puzzle_suitability": puzzle,
        "video_suitability": video,
        "date_relevance": date_pts,
    }
    score = sum(components.values())
    return ContentOpportunityResult(
        score=score,
        components=components,
        reasons={k: v for k, v in reasons.items() if v},
    )


def score_from_entities(
    *,
    game: Any,
    moment_classifications: Sequence[str],
    tactical_patterns: Sequence[str],
    today: date | None = None,
) -> ContentOpportunityResult:
    """Convenience wrapper over ORM-ish game objects."""
    return compute_content_opportunity(
        is_famous=bool(getattr(game, "is_famous", False)),
        famous_title=getattr(game, "famous_title", None),
        historical_tags=getattr(game, "historical_tags", None) or [],
        white_rating=getattr(game, "white_rating", None),
        black_rating=getattr(game, "black_rating", None),
        opening=getattr(game, "opening", None),
        eco=getattr(game, "eco", None),
        move_count=int(getattr(game, "move_count", 0) or 0),
        game_date=getattr(game, "game_date", None),
        moment_classifications=moment_classifications,
        tactical_patterns=tactical_patterns,
        today=today,
    )


def result_to_dict(result: ContentOpportunityResult) -> dict[str, Any]:
    return {
        "score": result.score,
        "components": dict(result.components),
        "reasons": dict(result.reasons),
        "formula_version": result.formula_version,
        "component_caps": dict(COMPONENT_CAPS),
    }

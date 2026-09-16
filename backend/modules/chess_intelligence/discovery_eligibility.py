"""§21 — inexpensive pre-analysis filter for recent discovery.

Flow::

    recent provider discovery → new ChessGame → eligibility → Stockfish
         → critical moments → tactical patterns → content opportunity
         → editorial candidate

Stockfish is **opt-in** (config/job ``auto_analyze``). Never mark discovered
games famous. Reuses ``ChessCriticalMoment`` / ``ChessTacticalPattern`` /
``ChessContentOpportunityScore`` via the existing analysis persist path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from backend.core.config import settings
from backend.modules.chess_intelligence.catalog_concepts import _event_looks_notable
from backend.modules.chess_intelligence.fingerprint import normalize_player_name
from backend.modules.chess_intelligence.models import ChessGame

# Default cheap gates when auto-analyze is enabled without job overrides.
DEFAULT_MIN_RATING = 2400
DEFAULT_REQUIRE_DECISIVE_RESULT = False


@dataclass(frozen=True, slots=True)
class DiscoveryAnalysisPolicy:
    """Whether / how recent discovery may enqueue Stockfish."""

    auto_analyze: bool = False
    min_rating: int | None = DEFAULT_MIN_RATING
    require_notable_event: bool = False
    event_whitelist: tuple[str, ...] = ()
    player_whitelist: tuple[str, ...] = ()
    allowed_results: tuple[str, ...] = ()  # empty = any
    max_analyze_per_sync: int = 5
    new_games_only: bool = True


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    eligible: bool
    reasons: tuple[str, ...] = ()


def policy_from_params(params: dict[str, Any] | None) -> DiscoveryAnalysisPolicy:
    """Merge job params over settings. Default auto_analyze=False (§21)."""
    raw = params or {}
    if "auto_analyze" in raw:
        auto = bool(raw.get("auto_analyze"))
    else:
        auto = bool(settings.CHESS_DISCOVERY_AUTO_ANALYZE_ENABLED)

    def _int(key: str, default: int | None) -> int | None:
        if key not in raw or raw.get(key) in (None, ""):
            return default
        return int(raw[key])

    def _str_tuple(key: str) -> tuple[str, ...]:
        val = raw.get(key)
        if val is None:
            return ()
        if isinstance(val, str):
            # Comma-separated tokens preserve multi-word events ("Tata Steel").
            if "," in val:
                return tuple(p.strip() for p in val.split(",") if p.strip())
            return tuple(p.strip() for p in val.split() if p.strip())
        return tuple(str(p).strip() for p in val if str(p).strip())

    min_rating = _int("analyze_min_rating", None)
    if min_rating is None:
        min_rating = _int("min_rating", settings.CHESS_DISCOVERY_AUTO_ANALYZE_MIN_RATING)

    require_event = raw.get("analyze_require_notable_event")
    if require_event is None:
        require_event = settings.CHESS_DISCOVERY_AUTO_ANALYZE_REQUIRE_NOTABLE_EVENT

    whitelist = _str_tuple("analyze_event_whitelist") or _str_tuple("event_whitelist")
    if not whitelist and settings.CHESS_DISCOVERY_AUTO_ANALYZE_EVENT_WHITELIST.strip():
        whitelist = tuple(
            p.strip()
            for p in settings.CHESS_DISCOVERY_AUTO_ANALYZE_EVENT_WHITELIST.split(",")
            if p.strip()
        )

    players = _str_tuple("analyze_player_whitelist") or _str_tuple("player_whitelist")
    results = _str_tuple("analyze_results") or _str_tuple("allowed_results")
    max_n = _int("analyze_max_per_sync", settings.CHESS_DISCOVERY_AUTO_ANALYZE_MAX_PER_SYNC)
    new_only = raw.get("analyze_new_games_only")
    if new_only is None:
        new_only = True

    return DiscoveryAnalysisPolicy(
        auto_analyze=auto,
        min_rating=min_rating,
        require_notable_event=bool(require_event),
        event_whitelist=whitelist,
        player_whitelist=players,
        allowed_results=results,
        max_analyze_per_sync=max(1, int(max_n or 5)),
        new_games_only=bool(new_only),
    )


def evaluate_analysis_eligibility(
    game: ChessGame,
    policy: DiscoveryAnalysisPolicy,
    *,
    created_game: bool,
) -> EligibilityDecision:
    """Cheap pre-Stockfish gate — ratings / event / result / player lists."""
    if not policy.auto_analyze:
        return EligibilityDecision(False, ("auto_analyze_disabled",))
    if policy.new_games_only and not created_game:
        return EligibilityDecision(False, ("existing_game_skip",))

    reasons: list[str] = []

    if policy.min_rating is not None:
        ratings = [r for r in (game.white_rating, game.black_rating) if r is not None]
        if not ratings or max(ratings) < policy.min_rating:
            return EligibilityDecision(False, ("below_min_rating",))
        reasons.append(f"rating>={policy.min_rating}")

    if policy.allowed_results:
        result = (game.result or "").strip()
        if result not in policy.allowed_results:
            return EligibilityDecision(False, ("result_not_allowed",))
        reasons.append(f"result={result}")

    if policy.player_whitelist:
        needles = {normalize_player_name(p) for p in policy.player_whitelist}
        white = normalize_player_name(game.white_player)
        black = normalize_player_name(game.black_player)
        if not any(n and (n in white or n in black) for n in needles):
            return EligibilityDecision(False, ("player_not_whitelisted",))
        reasons.append("player_whitelist")

    event_ok = False
    if policy.event_whitelist:
        event_n = normalize_player_name(game.event)
        for token in policy.event_whitelist:
            if normalize_player_name(token) and normalize_player_name(token) in event_n:
                event_ok = True
                reasons.append("event_whitelist")
                break
        if not event_ok:
            return EligibilityDecision(False, ("event_not_whitelisted",))
    elif policy.require_notable_event:
        if not _event_looks_notable(game.event):
            return EligibilityDecision(False, ("event_not_notable",))
        reasons.append("notable_event")
    elif _event_looks_notable(game.event):
        reasons.append("notable_event")

    # Never treat eligibility as fame.
    if game.is_famous:
        reasons.append("already_famous_unchanged")

    return EligibilityDecision(True, tuple(reasons) or ("eligible",))


def discovery_must_not_set_famous() -> bool:
    """Contract helper for tests/docs — discovery never classifies fame."""
    return True


def summarize_eligibility_batch(decisions: Sequence[EligibilityDecision]) -> dict[str, int]:
    return {
        "eligible": sum(1 for d in decisions if d.eligible),
        "ineligible": sum(1 for d in decisions if not d.eligible),
    }

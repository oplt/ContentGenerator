"""Phase 17 — transparent content opportunity scoring."""

from __future__ import annotations

from datetime import date

from backend.modules.chess_intelligence.content_opportunity import (
    COMPONENT_CAPS,
    compute_content_opportunity,
)


def test_component_caps_sum_to_100() -> None:
    assert sum(COMPONENT_CAPS.values()) == 100


def test_famous_game_scores_higher_than_plain() -> None:
    plain = compute_content_opportunity(move_count=40)
    famous = compute_content_opportunity(
        is_famous=True,
        famous_title="Immortal Game",
        historical_tags=["romantic", "sacrifice"],
        move_count=40,
        opening="King's Gambit",
    )
    assert famous.score > plain.score
    assert famous.components["historical_significance"] > 0
    assert famous.score == sum(famous.components.values())


def test_tactics_and_swings_add_explainable_points() -> None:
    result = compute_content_opportunity(
        move_count=24,
        moment_classifications=[
            "large_evaluation_swing",
            "blunder",
            "forced_mate",
        ],
        tactical_patterns=["fork", "queen_sacrifice"],
    )
    assert result.components["tactical_intensity"] > 0
    assert result.components["evaluation_swing"] > 0
    assert result.components["puzzle_suitability"] > 0
    assert "fork+3" in result.reasons.get("tactical_intensity", [])
    assert result.formula_version == "content_opportunity_v1"


def test_anniversary_date_relevance() -> None:
    result = compute_content_opportunity(
        game_date="1851.06.21",
        today=date(2026, 6, 21),
    )
    assert result.components["date_relevance"] == 6
    assert "anniversary_today" in result.reasons["date_relevance"]


def test_player_fame_from_ratings_only() -> None:
    result = compute_content_opportunity(white_rating=2750, black_rating=2400)
    assert result.components["player_fame"] >= 5
    assert any("white_rating" in r for r in result.reasons["player_fame"])

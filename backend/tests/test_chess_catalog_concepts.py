"""§8 — famous / recent-notable / content-opportunity are separate concepts."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.modules.chess_intelligence.catalog_concepts import (
    FAMOUS_RECENT_YEAR_FLOOR,
    classify_game,
    derive_is_notable,
    derive_is_recent,
)
from backend.modules.chess_intelligence.ingestion_mode import (
    METADATA_KEY,
    ChessIngestionMode,
)


def test_famous_classic_is_not_recent_or_notable() -> None:
    flags = classify_game(
        is_famous=True,
        year=1851,
        game_date="1851.06.21",
        created_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        source_metadata={"ingestion_mode": "historical_bootstrap"},
        white_rating=None,
        black_rating=None,
        event="London",
        content_opportunity_score=80,
        now=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert flags.is_famous is True
    assert flags.is_recent is False
    assert flags.is_notable is False


def test_recent_discovery_high_rated_is_notable_not_famous() -> None:
    flags = classify_game(
        is_famous=False,
        year=2026,
        game_date="2026.09.15",
        created_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        source_metadata={METADATA_KEY: ChessIngestionMode.RECENT_DISCOVERY.value},
        white_rating=2750,
        black_rating=2720,
        event="Sinquefield Cup",
        content_opportunity_score=62,
        now=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert flags.is_famous is False
    assert flags.is_recent is True
    assert flags.is_notable is True


def test_content_opportunity_score_alone_does_not_set_famous() -> None:
    flags = classify_game(
        is_famous=False,
        year=2020,
        game_date="2020.01.01",
        created_at=datetime(2020, 1, 2, tzinfo=timezone.utc),
        source_metadata={},
        content_opportunity_score=95,
        now=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert flags.is_famous is False
    assert flags.is_recent is False
    # High score alone without recent/ratings/event is not enough for notable.
    assert flags.is_notable is False


def test_editorial_notable_tag_wins() -> None:
    assert (
        derive_is_notable(
            is_famous=False,
            is_recent=False,
            historical_tags=["notable"],
        )
        is True
    )


def test_famous_year_floor_constant() -> None:
    assert FAMOUS_RECENT_YEAR_FLOOR == 1990
    assert (
        derive_is_recent(
            is_famous=True,
            year=1985,
            game_date=None,
            created_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            source_metadata={METADATA_KEY: ChessIngestionMode.RECENT_DISCOVERY.value},
        )
        is False
    )


def test_no_is_notable_column_on_orm() -> None:
    from backend.modules.chess_intelligence.models import ChessGame

    cols = {c.name for c in ChessGame.__table__.columns}
    assert "is_notable" not in cols
    assert "is_recent" not in cols
    assert "is_famous" in cols

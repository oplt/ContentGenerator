"""Phase 20 — external source rules (API / bulk / editorial; no curated scrapers)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.modules.chess_intelligence.source_rules import (
    ChessSourceRuleError,
    FORBIDDEN_SCRAPE_HOSTS,
    IntegrationMode,
    assert_bulk_file_allowed,
    assert_live_http_allowed,
    assert_provider_allowed_for_ingest,
    assert_url_not_scrape_target,
    get_provider_rule,
    live_http_providers,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CHESS_ROOT = REPO_ROOT / "backend" / "modules" / "chess_intelligence"


def test_documented_api_providers_allow_live_http() -> None:
    for provider in ("lichess_masters", "lichess_puzzles", "chesscom"):
        assert assert_live_http_allowed(provider) == provider
        rule = get_provider_rule(provider)
        assert rule is not None
        assert rule.mode == IntegrationMode.DOCUMENTED_API
        assert rule.allows_live_http is True


def test_puzzle_dataset_allows_bulk_file() -> None:
    assert assert_bulk_file_allowed("lichess_puzzles") == "lichess_puzzles"
    rule = get_provider_rule("lichess_puzzles")
    assert rule is not None
    assert rule.allows_bulk_file is True


def test_pgn_archive_and_custom_batch_labels() -> None:
    assert assert_bulk_file_allowed("pgn_archive") == "pgn_archive"
    assert assert_provider_allowed_for_ingest("twic_1600") == "twic_1600"
    assert assert_provider_allowed_for_ingest("local_wch") == "local_wch"


def test_rejects_chessgames_scraper_labels() -> None:
    for bad in ("chessgames", "chessgames_scraper", "scraped_chessgames", "html_crawler"):
        with pytest.raises(ChessSourceRuleError):
            assert_provider_allowed_for_ingest(bad)


def test_rejects_automated_fetch_of_curated_hosts() -> None:
    with pytest.raises(ChessSourceRuleError):
        assert_url_not_scrape_target(
            "https://www.chessgames.com/perl/chessgame?gid=1",
            for_automated_fetch=True,
        )
    # Editorial citation is allowed when not fetching.
    assert_url_not_scrape_target(
        "https://www.chessgames.com/perl/chessgame?gid=1",
        for_automated_fetch=False,
    )


def test_manual_import_rejects_scrape_url_when_provider_is_api_like() -> None:
    # Provider itself must be allowed first.
    with pytest.raises(ChessSourceRuleError):
        assert_provider_allowed_for_ingest("chessgames_import")


def test_live_http_set_matches_adapters() -> None:
    live = live_http_providers()
    assert "lichess_masters" in live
    assert "chesscom" in live
    assert "famous_catalog" not in live
    assert "pgn_archive" not in live


def test_no_chessgames_scraper_modules() -> None:
    forbidden_snippets = (
        "chessgames.com",
        "scrapy",
        "BeautifulSoup",
        "html.parser",
    )
    offenders: list[str] = []
    for path in CHESS_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT).as_posix()
        # Docs/comments may mention the ban; only flag fetch-shaped modules.
        if path.name in {"source_rules.py", "famous_catalog.py"}:
            continue
        if "scrape" in path.name.lower() or "chessgames" in path.name.lower():
            offenders.append(rel)
            continue
        if any(s in text for s in ("chessgames.com/perl", "from bs4", "import scrapy")):
            offenders.append(rel)
    assert offenders == [], f"Forbidden scraper-shaped chess modules: {offenders}"
    assert "chessgames.com" in FORBIDDEN_SCRAPE_HOSTS or "www.chessgames.com" in FORBIDDEN_SCRAPE_HOSTS


def test_gitignore_excludes_lichess_puzzle_dumps() -> None:
    ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "lichess_db_puzzle" in ignore
    assert "pgn_archives" in ignore


def test_providers_package_exports_only_documented_adapters() -> None:
    from backend.modules.chess_intelligence import providers as pkg

    assert hasattr(pkg, "LichessMastersProvider")
    assert hasattr(pkg, "LichessPuzzlesProvider")
    assert hasattr(pkg, "ChessComProvider")
    assert not hasattr(pkg, "ChessgamesScraper")

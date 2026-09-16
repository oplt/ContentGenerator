"""Phase 1 chess_intelligence domain: fingerprints, moves, normalizer."""

from __future__ import annotations

import uuid

from backend.modules.chess_intelligence.fingerprint import (
    compute_content_hash,
    compute_game_fingerprint,
    compute_puzzle_fingerprint,
)
from backend.modules.chess_intelligence.moves import annotate_moves
from backend.modules.chess_intelligence.normalizer import (
    chess_game_from_parsed,
    chess_puzzle_from_fields,
    year_from_pgn_date,
)
from backend.modules.chess_intelligence.schemas import ChessGameResponse, ChessPuzzleResponse
from backend.modules.chess_video.parser import parse_chess_input

PGN_SAMPLE = """
[Event "World Championship"]
[Site "New York"]
[Round "1"]
[White "Kasparov"]
[Black "Karpov"]
[Result "1-0"]
[Date "1990.10.01"]
[ECO "B33"]
[Opening "Sicilian"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 1-0
"""


def test_game_fingerprint_stable_and_move_sensitive() -> None:
    a = compute_game_fingerprint(
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        uci_moves=["e2e4", "e7e5"],
        result="1-0",
    )
    b = compute_game_fingerprint(
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        uci_moves=["e2e4", "e7e5"],
        result="1-0",
    )
    c = compute_game_fingerprint(
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        uci_moves=["e2e4", "c7c5"],
        result="1-0",
    )
    assert a == b
    assert a != c
    assert len(a) == 64


def test_content_hash_strips_whitespace() -> None:
    assert compute_content_hash("1. e4 e5\n") == compute_content_hash("1. e4 e5")


def test_year_from_pgn_date() -> None:
    assert year_from_pgn_date("1990.10.01") == 1990
    assert year_from_pgn_date("????.??.??") is None
    assert year_from_pgn_date(None) is None


def test_annotate_moves_ply_side_fens() -> None:
    parsed = parse_chess_input("1. e4 e5 2. Nf3", "san")
    moves = annotate_moves(parsed)
    assert len(moves) == 3
    assert moves[0].ply == 1
    assert moves[0].move_number == 1
    assert moves[0].side == "white"
    assert moves[0].san == "e4"
    assert moves[0].uci == "e2e4"
    assert moves[0].fen_before.startswith("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")
    assert moves[0].fen_after != moves[0].fen_before
    assert "e2e4" == moves[0].uci or moves[0].uci.startswith("e2")
    assert moves[1].side == "black"
    assert moves[1].move_number == 1
    assert moves[2].side == "white"
    assert moves[2].move_number == 2
    assert moves[2].fen_before == moves[1].fen_after


def test_chess_game_from_parsed_fills_canonical_fields() -> None:
    tenant_id = uuid.uuid4()
    parsed = parse_chess_input(PGN_SAMPLE, "pgn")
    game = chess_game_from_parsed(
        tenant_id=tenant_id,
        parsed=parsed,
        source_provider="manual",
        source_external_id="demo-1",
        source_url="https://example.test/game/1",
        source_metadata={"raw": {"id": "demo-1"}},
        is_famous=True,
        famous_title="Demo Classic",
        historical_tags=["demo"],
    )
    assert game.tenant_id == tenant_id
    assert game.white_player == "Kasparov"
    assert game.black_player == "Karpov"
    assert game.event == "World Championship"
    assert game.site == "New York"
    assert game.round == "1"
    assert game.year == 1990
    assert game.eco == "B33"
    assert game.opening == "Sicilian"
    assert game.move_count == 7
    assert game.normalized_pgn
    assert game.game_fingerprint == compute_game_fingerprint(
        starting_fen=parsed.starting_fen,
        uci_moves=parsed.uci_moves,
        result=parsed.result,
    )
    assert game.content_hash == compute_content_hash(parsed.normalized_pgn)
    assert game.is_famous is True
    assert game.famous_title == "Demo Classic"
    assert game.historical_tags == ["demo"]
    assert game.source_metadata["raw"]["id"] == "demo-1"

    # Pydantic round-trip shape (timestamps optional until flush)
    game.id = uuid.uuid4()
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    game.created_at = now
    game.updated_at = now
    response = ChessGameResponse.model_validate(game)
    assert response.move_count == 7
    assert response.source_provider == "manual"


def test_chess_puzzle_from_fields() -> None:
    tenant_id = uuid.uuid4()
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
    puzzle = chess_puzzle_from_fields(
        tenant_id=tenant_id,
        external_id="abc123",
        provider="lichess",
        starting_fen=fen,
        solution_moves_uci=["f3e5", "c6e5", "d1h5"],
        solution_moves_san=["Nxe5", "Nxe5", "Qh5"],
        rating=1600,
        themes=["fork", "short"],
    )
    assert puzzle.provider == "lichess"
    assert puzzle.solution_moves_uci[0] == "f3e5"
    assert puzzle.puzzle_fingerprint == compute_puzzle_fingerprint(
        starting_fen=fen,
        solution_moves_uci=["f3e5", "c6e5", "d1h5"],
    )
    assert len(puzzle.content_hash) == 64

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    puzzle.id = uuid.uuid4()
    puzzle.created_at = now
    puzzle.updated_at = now
    assert ChessPuzzleResponse.model_validate(puzzle).rating == 1600


def test_same_moves_same_fingerprint_across_formats() -> None:
    tenant_id = uuid.uuid4()
    from_san = chess_game_from_parsed(
        tenant_id=tenant_id,
        parsed=parse_chess_input("1. e4 e5 2. Nf3 Nc6", "san"),
    )
    from_uci = chess_game_from_parsed(
        tenant_id=tenant_id,
        parsed=parse_chess_input("e2e4 e7e5 g1f3 b8c6", "uci"),
    )
    assert from_san.game_fingerprint == from_uci.game_fingerprint

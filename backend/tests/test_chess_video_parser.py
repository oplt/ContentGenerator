"""Tests for chess move parser (PGN / SAN / UCI)."""

from __future__ import annotations

import pytest

from backend.modules.chess_video.parser import ChessParseError, parse_chess_input

PGN_SAMPLE = """
[Event "World Championship"]
[White "Kasparov"]
[Black "Karpov"]
[Result "1-0"]
[Date "1990.10.01"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 1-0
"""

SAN_SAMPLE = """
1. e4 e5
2. Nf3 Nc6
3. Bb5 a6
4. Ba4 Nf6
"""

UCI_SAMPLE = "e2e4 e7e5 g1f3 b8c6 f1b5"


def test_parse_normal_pgn() -> None:
    parsed = parse_chess_input(PGN_SAMPLE, "pgn")
    assert parsed.input_format == "pgn"
    assert parsed.white_player == "Kasparov"
    assert parsed.black_player == "Karpov"
    assert parsed.event == "World Championship"
    assert parsed.date == "1990.10.01"
    assert parsed.result == "1-0"
    assert parsed.move_count == 7
    assert parsed.san_moves[0] == "e4"
    assert parsed.uci_moves[0] == "e2e4"
    assert "[White \"Kasparov\"]" in parsed.normalized_pgn


def test_parse_raw_san() -> None:
    parsed = parse_chess_input(SAN_SAMPLE, "san")
    assert parsed.input_format == "san"
    assert parsed.move_count == 8
    assert parsed.san_moves == ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6"]
    assert parsed.uci_moves[0] == "e2e4"


def test_parse_raw_uci() -> None:
    parsed = parse_chess_input(UCI_SAMPLE, "uci")
    assert parsed.input_format == "uci"
    assert parsed.move_count == 5
    assert parsed.uci_moves == ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]
    assert parsed.san_moves[0] == "e4"


def test_auto_detect_formats() -> None:
    assert parse_chess_input(PGN_SAMPLE).input_format == "pgn"
    assert parse_chess_input(SAN_SAMPLE).input_format == "san"
    assert parse_chess_input(UCI_SAMPLE).input_format == "uci"


def test_same_internal_representation_across_formats() -> None:
    san = "1. e4 e5 2. Nf3 Nc6"
    uci = "e2e4 e7e5 g1f3 b8c6"
    from_san = parse_chess_input(san, "san")
    from_uci = parse_chess_input(uci, "uci")
    assert from_san.uci_moves == from_uci.uci_moves
    assert from_san.san_moves == from_uci.san_moves
    assert from_san.final_fen == from_uci.final_fen


def test_castling() -> None:
    # Minimal castling sequence
    text = "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 e1g1"
    parsed = parse_chess_input(text, "uci")
    assert "O-O" in parsed.san_moves
    assert "e1g1" in parsed.uci_moves


def test_promotion() -> None:
    # White pawn promotes on a8
    fen_game = """
[SetUp "1"]
[FEN "8/P7/8/8/8/8/8/4K2k w - - 0 1"]
[Result "*"]

1. a8=Q
"""
    parsed = parse_chess_input(fen_game, "pgn")
    assert parsed.move_count == 1
    assert parsed.uci_moves[0] == "a7a8q"
    assert parsed.san_moves[0].startswith("a8=Q")


def test_underpromotion() -> None:
    fen_game = """
[SetUp "1"]
[FEN "8/P7/8/8/8/8/8/4K2k w - - 0 1"]
[Result "*"]

1. a8=N
"""
    parsed = parse_chess_input(fen_game, "pgn")
    assert parsed.uci_moves[0] == "a7a8n"
    assert "N" in parsed.san_moves[0]


def test_en_passant() -> None:
    text = "e2e4 a7a6 e4e5 d7d5 e5d6"
    parsed = parse_chess_input(text, "uci")
    assert parsed.uci_moves[-1] == "e5d6"
    assert "xd6" in parsed.san_moves[-1] or parsed.san_moves[-1] == "exd6"


def test_check_and_checkmate() -> None:
    # Fool's mate
    text = "1. f3 e5 2. g4 Qh4#"
    parsed = parse_chess_input(text, "san")
    assert parsed.san_moves[-1].endswith("#")
    assert parsed.move_count == 4


def test_custom_fen() -> None:
    pgn = """
[SetUp "1"]
[FEN "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"]
[Result "*"]

1. Nf3
"""
    parsed = parse_chess_input(pgn, "pgn")
    assert "4p3/4P3" in parsed.starting_fen
    assert parsed.san_moves == ["Nf3"]
    assert parsed.move_count == 1


def test_invalid_move_includes_ply_and_fen() -> None:
    with pytest.raises(ChessParseError) as exc:
        parse_chess_input("1. e4 e5 2. Qh8", "san")
    message = str(exc.value)
    assert "Illegal move at ply" in message
    assert "Qh8" in message
    assert "Position:" in message
    assert "/" in message  # FEN ranks


def test_malformed_pgn() -> None:
    with pytest.raises(ChessParseError) as exc:
        parse_chess_input(
            """
[Event "Broken"]
[Result "*"]

1. e4 e5 2. Qh8
""",
            "pgn",
        )
    assert "Malformed PGN" in str(exc.value) or "Illegal" in str(exc.value)


def test_rejects_oversized_input() -> None:
    huge = "x" * (2 * 1024 * 1024 + 1)
    with pytest.raises(ChessParseError, match="maximum size"):
        parse_chess_input(huge, "uci")


def test_rejects_excess_plies(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.modules.chess_video.parser as parser_mod

    monkeypatch.setattr(parser_mod, "MAX_PLIES", 4)
    # 5 plies exceeds the patched limit.
    with pytest.raises(ChessParseError, match="maximum of 4 plies"):
        parse_chess_input("e2e4 e7e5 g1f3 b8c6 f1b5", "uci")

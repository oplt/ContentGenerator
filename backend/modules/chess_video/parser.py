"""Chess move / PGN parser — normalize PGN, SAN, and UCI into one representation."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from collections.abc import Callable
from typing import Literal

import chess
import chess.pgn

InputFormat = Literal["pgn", "san", "uci", "auto"]
DetectedFormat = Literal["pgn", "san", "uci"]

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_PLIES = 1000

_RESULT_TOKENS = frozenset({"1-0", "0-1", "1/2-1/2", "*"})
_UCI_MOVE_RE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$", re.IGNORECASE)
_HEADER_LINE_RE = re.compile(r'^\s*\[([A-Za-z0-9_]+)\s+"([^"]*)"\]\s*$')


class ChessParseError(ValueError):
    """Raised when chess input cannot be normalized."""


@dataclass(slots=True)
class ParsedChessGame:
    input_format: DetectedFormat
    headers: dict[str, str]
    starting_fen: str
    normalized_pgn: str
    moves: list[chess.Move]
    san_moves: list[str]
    uci_moves: list[str]
    move_count: int
    final_fen: str
    result: str | None
    white_player: str | None
    black_player: str | None
    event: str | None
    date: str | None


def parse_chess_input(source_text: str, input_format: InputFormat = "auto") -> ParsedChessGame:
    """Parse PGN / SAN / UCI (or auto-detect) into a normalized game."""
    if not isinstance(source_text, str):
        raise ChessParseError("Input must be text.")
    if len(source_text.encode("utf-8", errors="replace")) > MAX_INPUT_BYTES:
        raise ChessParseError(
            f"Input exceeds maximum size of {MAX_INPUT_BYTES // (1024 * 1024)} MB."
        )
    text = source_text.strip()
    if not text:
        raise ChessParseError("Input is empty.")

    detected: DetectedFormat
    if input_format == "auto":
        detected = _detect_format(text)
    elif input_format in {"pgn", "san", "uci"}:
        detected = input_format
    else:
        raise ChessParseError(f"Unsupported input format: {input_format}")

    if detected == "pgn":
        return _parse_pgn(text)
    if detected == "uci":
        return _parse_uci(text)
    return _parse_san(text)


def _detect_format(text: str) -> DetectedFormat:
    first = text.splitlines()[0].strip()
    if _HEADER_LINE_RE.match(first) or (_HEADER_LINE_RE.search(text) and "[" in text):
        return "pgn"
    tokens = _tokenize_moves(text)
    move_tokens = [tok for tok in tokens if tok not in _RESULT_TOKENS]
    if move_tokens and all(_UCI_MOVE_RE.match(tok) for tok in move_tokens):
        return "uci"
    return "san"


def _tokenize_moves(text: str) -> list[str]:
    cleaned = re.sub(r"\{[^}]*\}", " ", text)
    cleaned = re.sub(r";[^\n]*", " ", cleaned)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = re.sub(r"\$\d+", " ", cleaned)
    cleaned = re.sub(r"\d+\.(\.\.)?", " ", cleaned)
    return [tok for tok in cleaned.split() if tok]


def _starting_board_from_headers(headers: dict[str, str]) -> chess.Board:
    fen = headers.get("FEN")
    if not fen:
        return chess.Board()
    try:
        return chess.Board(fen)
    except ValueError as exc:
        raise ChessParseError(f"Invalid starting FEN: {fen}") from exc


def _illegal_move_message(ply: int, move_text: str, board: chess.Board) -> str:
    return f"Illegal move at ply {ply}: {move_text}\n\nPosition:\n{board.fen()}"


def _build_result(
    *,
    input_format: DetectedFormat,
    headers: dict[str, str],
    starting_fen: str,
    moves: list[chess.Move],
    san_moves: list[str],
    result: str | None,
) -> ParsedChessGame:
    if len(moves) > MAX_PLIES:
        raise ChessParseError(f"Game exceeds maximum of {MAX_PLIES} plies.")

    board = chess.Board(starting_fen)
    game = chess.pgn.Game()
    for key, value in headers.items():
        game.headers[key] = value
    if starting_fen != chess.STARTING_FEN:
        game.headers["SetUp"] = "1"
        game.headers["FEN"] = starting_fen
    if result:
        game.headers["Result"] = result
    elif "Result" not in game.headers:
        game.headers["Result"] = "*"

    node: chess.pgn.GameNode = game
    for move in moves:
        node = node.add_variation(move)
        board.push(move)

    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    normalized_pgn = str(game.accept(exporter)).strip() + "\n"

    return ParsedChessGame(
        input_format=input_format,
        headers=dict(game.headers),
        starting_fen=starting_fen,
        normalized_pgn=normalized_pgn,
        moves=moves,
        san_moves=san_moves,
        uci_moves=[move.uci() for move in moves],
        move_count=len(moves),
        final_fen=board.fen(),
        result=game.headers.get("Result"),
        white_player=game.headers.get("White"),
        black_player=game.headers.get("Black"),
        event=game.headers.get("Event"),
        date=game.headers.get("Date") or game.headers.get("UTCDate"),
    )


def _parse_pgn(text: str) -> ParsedChessGame:
    class _StrictGameBuilder(chess.pgn.GameBuilder[chess.pgn.Game]):
        def handle_error(self, error: Exception) -> None:
            raise ChessParseError(f"Malformed PGN: {error}") from error

    try:
        game = chess.pgn.read_game(io.StringIO(text), Visitor=_StrictGameBuilder)
    except ChessParseError:
        raise
    except Exception as exc:
        raise ChessParseError(f"Malformed PGN: {exc}") from exc
    if game is None:
        raise ChessParseError("Malformed PGN: no game found.")

    headers = {key: game.headers[key] for key in game.headers}
    board = _starting_board_from_headers(headers)
    starting_fen = board.fen()
    moves: list[chess.Move] = []
    san_moves: list[str] = []

    node: chess.pgn.GameNode = game
    ply = 0
    while node.variations:
        next_node = node.variation(0)
        move = next_node.move
        ply += 1
        if ply > MAX_PLIES:
            raise ChessParseError(f"Game exceeds maximum of {MAX_PLIES} plies.")
        if move not in board.legal_moves:
            raise ChessParseError(_illegal_move_message(ply, move.uci(), board))
        san_moves.append(board.san(move))
        board.push(move)
        moves.append(move)
        node = next_node

    return _build_result(
        input_format="pgn",
        headers=headers,
        starting_fen=starting_fen,
        moves=moves,
        san_moves=san_moves,
        result=headers.get("Result"),
    )


def _apply_token_moves(
    tokens: list[str],
    *,
    input_format: DetectedFormat,
    parse_token: Callable[[chess.Board, str], chess.Move],
) -> ParsedChessGame:
    board = chess.Board()
    starting_fen = board.fen()
    moves: list[chess.Move] = []
    san_moves: list[str] = []
    result: str | None = None
    ply = 0
    for token in tokens:
        if token in _RESULT_TOKENS:
            result = token
            continue
        ply += 1
        if ply > MAX_PLIES:
            raise ChessParseError(f"Game exceeds maximum of {MAX_PLIES} plies.")
        try:
            move = parse_token(board, token)
        except ChessParseError:
            raise
        except ValueError as exc:
            raise ChessParseError(_illegal_move_message(ply, token, board)) from exc
        if move not in board.legal_moves:
            raise ChessParseError(_illegal_move_message(ply, token, board))
        san_moves.append(board.san(move))
        board.push(move)
        moves.append(move)
    if not moves:
        raise ChessParseError(f"No legal {input_format.upper()} moves found.")
    return _build_result(
        input_format=input_format,
        headers={"Result": result or "*"},
        starting_fen=starting_fen,
        moves=moves,
        san_moves=san_moves,
        result=result or "*",
    )


def _parse_san(text: str) -> ParsedChessGame:
    def parse_token(board: chess.Board, token: str) -> chess.Move:
        return board.parse_san(token)

    return _apply_token_moves(_tokenize_moves(text), input_format="san", parse_token=parse_token)


def _parse_uci(text: str) -> ParsedChessGame:
    def parse_token(_board: chess.Board, token: str) -> chess.Move:
        return chess.Move.from_uci(token.lower())

    return _apply_token_moves(_tokenize_moves(text), input_format="uci", parse_token=parse_token)

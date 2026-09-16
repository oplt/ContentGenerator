"""Build canonical ChessGame / ChessPuzzle from parsed input or provider DTOs."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime
from typing import Any

import chess

from backend.modules.chess_intelligence.fingerprint import (
    compute_content_hash,
    compute_game_fingerprint,
    compute_puzzle_fingerprint,
)
from backend.modules.chess_intelligence.models import ChessGame, ChessPuzzle
from backend.modules.chess_intelligence.providers.dtos import (
    ExternalChessGame,
    ExternalChessPuzzle,
)
from backend.modules.chess_video.parser import ChessParseError, ParsedChessGame, parse_chess_input

_YEAR_RE = re.compile(r"^(\d{4})")


def year_from_pgn_date(game_date: str | None) -> int | None:
    if not game_date:
        return None
    match = _YEAR_RE.match(game_date.strip())
    if not match:
        return None
    year = int(match.group(1))
    if year < 1400 or year > 2100:
        return None
    return year


def chess_game_from_parsed(
    *,
    tenant_id: uuid.UUID,
    parsed: ParsedChessGame,
    source_provider: str | None = None,
    source_external_id: str | None = None,
    source_url: str | None = None,
    source_metadata: dict[str, Any] | None = None,
    white_rating: int | None = None,
    black_rating: int | None = None,
    white_player: str | None = None,
    black_player: str | None = None,
    event: str | None = None,
    site: str | None = None,
    round: str | None = None,
    game_date: str | None = None,
    year: int | None = None,
    result: str | None = None,
    eco: str | None = None,
    opening: str | None = None,
    variation: str | None = None,
    is_famous: bool = False,
    famous_title: str | None = None,
    historical_tags: list[str] | None = None,
) -> ChessGame:
    """Construct an unsaved ChessGame from ParsedChessGame (+ optional overrides)."""
    headers = parsed.headers
    resolved_date = game_date if game_date is not None else parsed.date
    return ChessGame(
        tenant_id=tenant_id,
        white_player=white_player if white_player is not None else parsed.white_player,
        black_player=black_player if black_player is not None else parsed.black_player,
        white_rating=white_rating,
        black_rating=black_rating,
        event=event if event is not None else parsed.event,
        site=site if site is not None else headers.get("Site"),
        round=round if round is not None else headers.get("Round"),
        game_date=resolved_date,
        year=year if year is not None else year_from_pgn_date(resolved_date),
        result=result if result is not None else parsed.result,
        eco=eco if eco is not None else headers.get("ECO"),
        opening=opening if opening is not None else headers.get("Opening"),
        variation=variation if variation is not None else headers.get("Variation"),
        starting_fen=parsed.starting_fen,
        final_fen=parsed.final_fen,
        normalized_pgn=parsed.normalized_pgn,
        move_count=parsed.move_count,
        source_provider=source_provider,
        source_external_id=source_external_id,
        source_url=source_url,
        source_metadata=dict(source_metadata or {}),
        content_hash=compute_content_hash(parsed.normalized_pgn),
        game_fingerprint=compute_game_fingerprint(
            starting_fen=parsed.starting_fen,
            uci_moves=parsed.uci_moves,
            result=result if result is not None else parsed.result,
        ),
        is_famous=is_famous,
        famous_title=famous_title,
        historical_tags=list(historical_tags or []),
    )


def normalize_external_game(
    *,
    tenant_id: uuid.UUID,
    external: ExternalChessGame,
) -> ChessGame:
    """Provider DTO → canonical ChessGame (parse + provenance; no raw JSON passthrough)."""
    parsed = parse_chess_input(external.pgn, "pgn")
    return chess_game_from_parsed(
        tenant_id=tenant_id,
        parsed=parsed,
        source_provider=external.provider,
        source_external_id=external.external_id,
        source_url=external.source_url,
        source_metadata=dict(external.source_metadata),
        white_rating=external.white_rating,
        black_rating=external.black_rating,
        white_player=external.white_player,
        black_player=external.black_player,
        event=external.event,
        site=external.site,
        round=external.round,
        game_date=external.game_date,
        year=external.year,
        result=external.result,
        eco=external.eco,
        opening=external.opening,
        variation=external.variation,
    )


def validate_puzzle_solution(*, starting_fen: str, solution_moves_uci: list[str]) -> list[str]:
    """Validate UCI solution against starting FEN; return SAN sequence."""
    try:
        board = chess.Board(starting_fen)
    except ValueError as exc:
        raise ChessParseError(f"Invalid puzzle FEN: {starting_fen}") from exc
    san_moves: list[str] = []
    for ply, token in enumerate(solution_moves_uci, start=1):
        try:
            move = chess.Move.from_uci(token)
        except ValueError as exc:
            raise ChessParseError(f"Invalid UCI at ply {ply}: {token}") from exc
        if move not in board.legal_moves:
            raise ChessParseError(
                f"Illegal puzzle move at ply {ply}: {token}\n\nPosition:\n{board.fen()}"
            )
        san_moves.append(board.san(move))
        board.push(move)
    if not san_moves:
        raise ChessParseError("Puzzle solution is empty.")
    return san_moves


def chess_puzzle_from_fields(
    *,
    tenant_id: uuid.UUID,
    external_id: str,
    provider: str,
    starting_fen: str,
    solution_moves_uci: list[str],
    solution_moves_san: list[str] | None = None,
    rating: int | None = None,
    rating_deviation: float | None = None,
    popularity: int | None = None,
    play_count: int | None = None,
    themes: list[str] | None = None,
    opening_tags: list[str] | None = None,
    source_game_id: str | None = None,
    source_game_url: str | None = None,
    source_metadata: dict[str, Any] | None = None,
    retrieved_at: datetime | None = None,
    import_batch_id: str | None = None,
    license_note: str | None = None,
) -> ChessPuzzle:
    """Construct an unsaved ChessPuzzle with fingerprints populated."""
    from backend.modules.chess_intelligence.licenses import license_for_provider

    uci = [m.strip().lower() for m in solution_moves_uci if m and m.strip()]
    meta = dict(source_metadata or {})
    raw = f"{starting_fen.strip()}|{' '.join(uci)}|{provider}:{external_id}"
    return ChessPuzzle(
        tenant_id=tenant_id,
        external_id=external_id,
        provider=provider,
        starting_fen=starting_fen.strip(),
        solution_moves_uci=uci,
        solution_moves_san=list(solution_moves_san or []),
        rating=rating,
        rating_deviation=rating_deviation,
        popularity=popularity,
        play_count=play_count,
        themes=list(themes or []),
        opening_tags=list(opening_tags or []),
        source_game_id=source_game_id,
        source_game_url=source_game_url,
        source_metadata=meta,
        retrieved_at=retrieved_at,
        import_batch_id=import_batch_id,
        license_note=license_note or license_for_provider(provider),
        puzzle_fingerprint=compute_puzzle_fingerprint(
            starting_fen=starting_fen,
            solution_moves_uci=uci,
        ),
        content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def normalize_external_puzzle(
    *,
    tenant_id: uuid.UUID,
    external: ExternalChessPuzzle,
    validate_solution: bool = True,
) -> ChessPuzzle:
    """Provider DTO → canonical ChessPuzzle (optional legal-move validation)."""
    san = list(external.solution_moves_san)
    if validate_solution:
        derived = validate_puzzle_solution(
            starting_fen=external.starting_fen,
            solution_moves_uci=external.solution_moves_uci,
        )
        if not san:
            san = derived
    return chess_puzzle_from_fields(
        tenant_id=tenant_id,
        external_id=external.external_id,
        provider=external.provider,
        starting_fen=external.starting_fen,
        solution_moves_uci=external.solution_moves_uci,
        solution_moves_san=san,
        rating=external.rating,
        rating_deviation=external.rating_deviation,
        popularity=external.popularity,
        play_count=external.play_count,
        themes=external.themes,
        opening_tags=external.opening_tags,
        source_game_id=external.source_game_id,
        source_game_url=external.source_game_url,
        source_metadata=dict(external.source_metadata),
    )

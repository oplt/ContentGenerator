"""Deterministic Pillow chess board frame renderer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chess
from PIL import Image, ImageDraw, ImageFont

from backend.modules.chess_video.presets import (
    DEFAULT_PRESET,
    RenderPreset,
    RenderPresetName,
    get_preset,
)
from backend.modules.chess_video.themes import (
    DEFAULT_BOARD_THEME,
    BoardTheme,
    BoardThemeName,
    get_board_theme,
)

RENDERER_VERSION = "1"

_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "pieces"
_BG = (18, 22, 28)
_FG = (236, 240, 244)
_MUTED = (160, 170, 180)

_PIECE_FILES = {
    chess.Piece(chess.PAWN, chess.WHITE): "wP.png",
    chess.Piece(chess.KNIGHT, chess.WHITE): "wN.png",
    chess.Piece(chess.BISHOP, chess.WHITE): "wB.png",
    chess.Piece(chess.ROOK, chess.WHITE): "wR.png",
    chess.Piece(chess.QUEEN, chess.WHITE): "wQ.png",
    chess.Piece(chess.KING, chess.WHITE): "wK.png",
    chess.Piece(chess.PAWN, chess.BLACK): "bP.png",
    chess.Piece(chess.KNIGHT, chess.BLACK): "bN.png",
    chess.Piece(chess.BISHOP, chess.BLACK): "bB.png",
    chess.Piece(chess.ROOK, chess.BLACK): "bR.png",
    chess.Piece(chess.QUEEN, chess.BLACK): "bQ.png",
    chess.Piece(chess.KING, chess.BLACK): "bK.png",
}


@dataclass(frozen=True, slots=True)
class FrameMeta:
    """Optional overlay metadata for a single board frame."""

    title: str | None = None
    white_player: str | None = None
    black_player: str | None = None
    event: str | None = None
    move_number: int | None = None
    last_san: str | None = None
    result: str | None = None
    show_coordinates: bool = True


class ChessVideoRenderer:
    """Render one chess position to a RGB PNG frame (Pillow, no browser)."""

    def __init__(
        self,
        preset: RenderPreset | RenderPresetName | None = None,
        *,
        board_theme: BoardTheme | BoardThemeName | None = None,
    ) -> None:
        if isinstance(preset, RenderPreset):
            self.preset = preset
        else:
            self.preset = get_preset(preset or DEFAULT_PRESET)
        if isinstance(board_theme, BoardTheme):
            self.board_theme = board_theme
        else:
            self.board_theme = get_board_theme(board_theme or DEFAULT_BOARD_THEME)
        self._piece_cache: dict[tuple[chess.Piece, int], Image.Image] = {}
        self._base_pieces = self._load_base_pieces()
        self._font_lg = self._load_font(max(28, self.preset.width // 22))
        self._font_md = self._load_font(max(22, self.preset.width // 28))
        self._font_sm = self._load_font(max(16, self.preset.width // 40))

    @staticmethod
    def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for path in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _load_base_pieces(self) -> dict[chess.Piece, Image.Image]:
        loaded: dict[chess.Piece, Image.Image] = {}
        for piece, filename in _PIECE_FILES.items():
            path = _ASSETS_DIR / filename
            if not path.is_file():
                raise FileNotFoundError(f"Missing chess piece asset: {path}")
            loaded[piece] = Image.open(path).convert("RGBA")
        return loaded

    def _piece_image(self, piece: chess.Piece, square_size: int) -> Image.Image:
        key = (piece, square_size)
        cached = self._piece_cache.get(key)
        if cached is not None:
            return cached
        base = self._base_pieces[piece]
        pad = max(2, square_size // 12)
        scaled = base.resize((square_size - 2 * pad, square_size - 2 * pad), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (square_size, square_size), (0, 0, 0, 0))
        canvas.paste(scaled, (pad, pad), scaled)
        self._piece_cache[key] = canvas
        return canvas

    def render_frame(
        self,
        board: chess.Board,
        *,
        last_move: chess.Move | None = None,
        meta: FrameMeta | None = None,
    ) -> Image.Image:
        meta = meta or FrameMeta()
        w, h = self.preset.width, self.preset.height
        img = Image.new("RGB", (w, h), _BG)
        draw = ImageDraw.Draw(img)

        margin_x = int(w * 0.06)
        header_h = int(h * 0.14)
        footer_h = int(h * 0.16)
        board_area_top = header_h
        board_area_bottom = h - footer_h
        board_max = min(w - 2 * margin_x, board_area_bottom - board_area_top)
        square = board_max // 8
        board_px = square * 8
        board_x = (w - board_px) // 2
        board_y = board_area_top + (board_area_bottom - board_area_top - board_px) // 2

        self._draw_header(draw, w, header_h, meta)
        self._draw_board(img, draw, board, board_x, board_y, square, last_move, meta.show_coordinates)
        self._draw_footer(draw, w, h, footer_h, board, meta)
        return img

    def render_png_bytes(
        self,
        board: chess.Board,
        *,
        last_move: chess.Move | None = None,
        meta: FrameMeta | None = None,
        compress_level: int = 1,
    ) -> bytes:
        frame = self.render_frame(board, last_move=last_move, meta=meta)
        try:
            import io

            buf = io.BytesIO()
            frame.save(buf, format="PNG", compress_level=compress_level)
            return buf.getvalue()
        finally:
            frame.close()

    def _draw_header(self, draw: ImageDraw.ImageDraw, width: int, header_h: int, meta: FrameMeta) -> None:
        pad = int(width * 0.06)
        y = int(header_h * 0.28)
        players = self._players_line(meta)
        if players:
            draw.text((pad, y), players, font=self._font_lg, fill=_FG)
            y += int(self._font_lg.getbbox(players)[3] * 1.35)
        subtitle = meta.title or meta.event
        if subtitle:
            draw.text((pad, y), subtitle, font=self._font_md, fill=_MUTED)

    @staticmethod
    def _players_line(meta: FrameMeta) -> str | None:
        if meta.white_player and meta.black_player:
            return f"{meta.white_player} vs {meta.black_player}"
        if meta.white_player:
            return meta.white_player
        if meta.black_player:
            return meta.black_player
        return None

    def _draw_board(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        board: chess.Board,
        origin_x: int,
        origin_y: int,
        square: int,
        last_move: chess.Move | None,
        show_coordinates: bool,
    ) -> None:
        board_px = square * 8
        edge = max(2, square // 16)
        draw.rectangle(
            [
                origin_x - edge,
                origin_y - edge,
                origin_x + board_px + edge,
                origin_y + board_px + edge,
            ],
            fill=self.board_theme.edge,
        )
        highlight = Image.new("RGBA", (board_px, board_px), (0, 0, 0, 0))
        hdraw = ImageDraw.Draw(highlight)
        for rank in range(8):
            for file in range(8):
                sq = chess.square(file, 7 - rank)
                x0, y0 = file * square, rank * square
                color = self.board_theme.light if (file + rank) % 2 == 0 else self.board_theme.dark
                draw.rectangle(
                    [origin_x + x0, origin_y + y0, origin_x + x0 + square, origin_y + y0 + square],
                    fill=color,
                )
                if last_move is not None and sq in (last_move.from_square, last_move.to_square):
                    tint = (
                        self.board_theme.highlight_from
                        if sq == last_move.from_square
                        else self.board_theme.highlight_to
                    )
                    hdraw.rectangle([x0, y0, x0 + square, y0 + square], fill=tint)
        img.paste(highlight, (origin_x, origin_y), highlight)
        highlight.close()

        for sq, piece in board.piece_map().items():
            file = chess.square_file(sq)
            rank = chess.square_rank(sq)
            x = origin_x + file * square
            y = origin_y + (7 - rank) * square
            piece_img = self._piece_image(piece, square)
            img.paste(piece_img, (x, y), piece_img)

        if show_coordinates:
            files = "abcdefgh"
            for i, ch in enumerate(files):
                draw.text(
                    (origin_x + i * square + square // 3, origin_y + board_px + 4),
                    ch,
                    font=self._font_sm,
                    fill=_MUTED,
                )
            for i in range(8):
                draw.text(
                    (origin_x - int(square * 0.35), origin_y + i * square + square // 3),
                    str(8 - i),
                    font=self._font_sm,
                    fill=_MUTED,
                )

    def _draw_footer(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
        footer_h: int,
        board: chess.Board,
        meta: FrameMeta,
    ) -> None:
        pad = int(width * 0.06)
        y = height - footer_h + int(footer_h * 0.2)
        move_line = self._move_line(meta)
        if move_line:
            draw.text((pad, y), move_line, font=self._font_lg, fill=_FG)
            y += int(self._font_lg.getbbox(move_line)[3] * 1.35)
        if meta.result and meta.result != "*":
            status = f"Result: {meta.result}"
        elif board.is_checkmate():
            status = "Checkmate"
        elif board.is_stalemate():
            status = "Stalemate"
        elif board.is_check():
            turn = "White" if board.turn == chess.WHITE else "Black"
            status = f"{turn} in check"
        else:
            turn = "White" if board.turn == chess.WHITE else "Black"
            status = f"{turn} to move"
        draw.text((pad, y), status, font=self._font_md, fill=_MUTED)

    @staticmethod
    def _move_line(meta: FrameMeta) -> str | None:
        if meta.last_san and meta.move_number is not None:
            # After Black's move, move_number is the completed full-move number.
            return f"{meta.move_number}. {meta.last_san}"
        if meta.last_san:
            return meta.last_san
        return None

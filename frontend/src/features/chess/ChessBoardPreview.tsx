/** Minimal FEN board preview (no chess.js dependency). */

const PIECES: Record<string, string> = {
  K: "♔",
  Q: "♕",
  R: "♖",
  B: "♗",
  N: "♘",
  P: "♙",
  k: "♚",
  q: "♛",
  r: "♜",
  b: "♝",
  n: "♞",
  p: "♟",
};

function parseFenBoard(fen: string): (string | null)[][] {
  const placement = fen.trim().split(/\s+/)[0] ?? "";
  const rows = placement.split("/");
  const board: (string | null)[][] = [];
  for (const row of rows.slice(0, 8)) {
    const cells: (string | null)[] = [];
    for (const ch of row) {
      if (ch >= "1" && ch <= "8") {
        for (let i = 0; i < Number(ch); i += 1) cells.push(null);
      } else {
        cells.push(ch);
      }
    }
    while (cells.length < 8) cells.push(null);
    board.push(cells.slice(0, 8));
  }
  while (board.length < 8) board.push(Array.from({ length: 8 }, () => null));
  return board.slice(0, 8);
}

export type ChessBoardPreviewProps = {
  fen: string;
  className?: string;
  size?: "sm" | "md";
};

export function ChessBoardPreview({ fen, className = "", size = "sm" }: ChessBoardPreviewProps) {
  const board = parseFenBoard(fen);
  const cell = size === "md" ? "size-8 text-lg" : "size-5 text-xs sm:size-6 sm:text-sm";
  return (
    <div
      className={`inline-grid grid-cols-8 overflow-hidden rounded border border-border shadow-sm ${className}`}
      role="img"
      aria-label="Chess position preview"
    >
      {board.map((row, rank) =>
        row.map((piece, file) => {
          const light = (rank + file) % 2 === 0;
          return (
            <div
              key={`${rank}-${file}`}
              className={`${cell} flex items-center justify-center ${
                light ? "bg-[#f0d9b5] text-[#1a1a1a]" : "bg-[#b58863] text-[#1a1a1a]"
              }`}
            >
              {piece ? PIECES[piece] ?? piece : null}
            </div>
          );
        }),
      )}
    </div>
  );
}

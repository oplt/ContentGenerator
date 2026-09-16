import type { ChessMove } from "../../api/chessData";

export type MoveViewerProps = {
  moves: ChessMove[];
  activePly?: number | null;
  onSelectPly?: (ply: number) => void;
};

export function MoveViewer({ moves, activePly = null, onSelectPly }: MoveViewerProps) {
  if (!moves.length) {
    return <p className="text-sm text-muted-foreground">No moves.</p>;
  }

  return (
    <ol className="max-h-64 space-y-1 overflow-y-auto rounded border border-border p-2 text-sm">
      {moves.map((move) => {
        const active = activePly === move.ply;
        return (
          <li key={move.ply}>
            <button
              type="button"
              className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left ${
                active ? "bg-primary/10 text-foreground" : "hover:bg-muted/40"
              }`}
              onClick={() => onSelectPly?.(move.ply)}
            >
              <span className="w-10 tabular-nums text-muted-foreground">
                {move.move_number}
                {move.side === "white" ? "." : "..."}
              </span>
              <span className="font-medium">{move.san}</span>
              <span className="ml-auto text-xs text-muted-foreground">{move.uci}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

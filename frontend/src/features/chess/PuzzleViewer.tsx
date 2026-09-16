import type { ChessPuzzle } from "../../api/chessData";
import { EmptyState } from "../../components/ui/EmptyState";
import { ChessBoardPreview } from "./ChessBoardPreview";

export type PuzzleViewerProps = {
  puzzle: ChessPuzzle | null;
  emptyMessage?: string;
};

/** Detail pane for a selected catalog / daily puzzle. */
export function PuzzleViewer({
  puzzle,
  emptyMessage = "Browse the puzzle catalog or open today's daily puzzle.",
}: PuzzleViewerProps) {
  if (!puzzle) {
    return (
      <EmptyState title="Select a puzzle" description={emptyMessage} />
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-medium">
        Puzzle {puzzle.provider}/{puzzle.external_id}
      </h3>
      <ChessBoardPreview fen={puzzle.starting_fen} size="md" />
      <p className="text-sm text-muted-foreground">
        Rating {puzzle.rating ?? "—"}
        {puzzle.themes.length ? ` · ${puzzle.themes.slice(0, 6).join(", ")}` : ""}
      </p>
      <p className="text-sm text-muted-foreground">
        Solution: {puzzle.solution_moves_san.join(" ") || "—"}
      </p>
      <p className="text-xs text-muted-foreground">
        Video from puzzles ships later — use Games for Create Video.
      </p>
    </div>
  );
}

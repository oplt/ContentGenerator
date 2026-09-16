import type { ChessPuzzle } from "../../api/chessData";
import { Card } from "../../components/ui/card";
import { ChessBoardPreview } from "./ChessBoardPreview";

export type PuzzleCardProps = {
  puzzle: ChessPuzzle;
  selected?: boolean;
  onSelect?: (puzzle: ChessPuzzle) => void;
};

export function PuzzleCard({ puzzle, selected = false, onSelect }: PuzzleCardProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect?.(puzzle)}
      className="w-full text-left"
      aria-pressed={selected}
    >
      <Card
        className={`flex gap-3 p-3 transition-colors ${
          selected ? "border-primary bg-primary/5" : "hover:bg-muted/30"
        }`}
      >
        <ChessBoardPreview fen={puzzle.starting_fen} />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="truncate text-sm font-medium text-foreground">
            {puzzle.provider}/{puzzle.external_id}
          </p>
          <p className="text-xs text-muted-foreground">
            {[
              puzzle.rating != null ? `rating ${puzzle.rating}` : null,
              puzzle.popularity != null ? `pop ${puzzle.popularity}` : null,
            ]
              .filter(Boolean)
              .join(" · ") || "—"}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            {puzzle.themes.slice(0, 4).join(", ") || "no themes"}
          </p>
        </div>
      </Card>
    </button>
  );
}

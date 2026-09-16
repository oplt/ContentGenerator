import { useState } from "react";
import type { ChessPuzzle, ChessPuzzleSearchParams } from "../../api/chessData";
import { Card } from "../../components/ui/card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { ChessListSkeleton } from "./ChessListSkeleton";
import { PuzzleCard } from "./PuzzleCard";
import { PuzzleFilters } from "./PuzzleFilters";
import { useChessPuzzles } from "./hooks/useChessPuzzles";

const DEFAULT: ChessPuzzleSearchParams = { limit: 20 };

export type PuzzleBrowserPanelProps = {
  selectedId?: string | null;
  onSelect: (puzzle: ChessPuzzle) => void;
};

export function PuzzleBrowserPanel({ selectedId = null, onSelect }: PuzzleBrowserPanelProps) {
  const [draft, setDraft] = useState<ChessPuzzleSearchParams>(DEFAULT);
  const [applied, setApplied] = useState<ChessPuzzleSearchParams>(DEFAULT);
  const listQuery = useChessPuzzles(applied);

  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-4">
        <div className="space-y-1">
          <h2 className="text-base font-medium text-foreground">Browse puzzles</h2>
          <p className="text-sm text-muted-foreground">
            Select tactics worth teaching or turning into short-form content.
          </p>
        </div>
        <PuzzleFilters
          value={draft}
          onChange={setDraft}
          onSubmit={() => setApplied({ ...draft })}
        />
      </Card>
      {listQuery.isLoading ? <ChessListSkeleton label="Searching puzzles" /> : null}
      {listQuery.isError ? (
        <ErrorState
          title="Could not search puzzles"
          message={listQuery.error instanceof Error ? listQuery.error.message : "Request failed"}
          onRetry={() => void listQuery.refetch()}
        />
      ) : null}
      <div className="grid gap-2">
        {(listQuery.data?.items ?? []).map((puzzle) => (
          <PuzzleCard
            key={puzzle.id}
            puzzle={puzzle}
            selected={selectedId === puzzle.id}
            onSelect={onSelect}
          />
        ))}
        {listQuery.isSuccess && (listQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="No matching puzzles"
            description="No puzzles matched these filters. Widen rating or clear themes."
          />
        ) : null}
      </div>
    </div>
  );
}

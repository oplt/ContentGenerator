import type { ChessPuzzle } from "../../api/chessData";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { ChessBoardPreview } from "./ChessBoardPreview";
import { useDailyChessPuzzle } from "./hooks/useChessPuzzles";

export type DailyPuzzlePanelProps = {
  selectedId?: string | null;
  onSelect: (puzzle: ChessPuzzle) => void;
};

export function DailyPuzzlePanel({ selectedId = null, onSelect }: DailyPuzzlePanelProps) {
  const dailyQuery = useDailyChessPuzzle(true);

  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-4">
        {dailyQuery.isLoading ? <LoadingState label="Fetching daily" /> : null}
        {dailyQuery.isError ? (
          <ErrorState
            title="Daily puzzle unavailable"
            message={
              dailyQuery.error instanceof Error ? dailyQuery.error.message : "Request failed"
            }
            onRetry={() => void dailyQuery.refetch()}
          />
        ) : null}
        {dailyQuery.data ? (
          <div className="flex flex-col gap-3 sm:flex-row">
            <ChessBoardPreview fen={dailyQuery.data.starting_fen} size="md" />
            <div className="space-y-2">
              <p className="text-sm font-medium">
                Daily · {dailyQuery.data.provider}/{dailyQuery.data.external_id}
              </p>
              <p className="text-xs text-muted-foreground">
                {dailyQuery.data.themes.join(", ") || "—"}
              </p>
              <Button
                type="button"
                size="sm"
                variant={selectedId === dailyQuery.data.id ? "default" : "secondary"}
                onClick={() => onSelect(dailyQuery.data!)}
              >
                {selectedId === dailyQuery.data.id ? "Selected" : "Select daily"}
              </Button>
            </div>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

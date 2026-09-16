import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ChessPuzzle } from "../../api/chessData";
import { refreshDailyChessPuzzle } from "../../api/chessData";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { useTenantScope } from "../../hooks/useTenantScope";
import { queryKeys } from "../../lib/queryKeys";
import { ChessBoardPreview } from "./ChessBoardPreview";
import { useDailyChessPuzzle } from "./hooks/useChessPuzzles";
import {
  dailyFreshnessLabel,
  formatDisplayDateTime,
} from "./sourceFreshness";

export type DailyPuzzlePanelProps = {
  selectedId?: string | null;
  onSelect: (puzzle: ChessPuzzle) => void;
};

export function DailyPuzzlePanel({ selectedId = null, onSelect }: DailyPuzzlePanelProps) {
  const { tenantId } = useTenantScope();
  const dailyQuery = useDailyChessPuzzle(true);
  const queryClient = useQueryClient();
  const dailyKey = queryKeys.chessDailyPuzzle(tenantId ?? "none");
  const refreshMutation = useMutation({
    mutationFn: () => refreshDailyChessPuzzle(),
    onSuccess: (puzzle) => {
      queryClient.setQueryData(dailyKey, puzzle);
      void queryClient.invalidateQueries({ queryKey: dailyKey });
    },
  });

  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium">Daily puzzle</p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={refreshMutation.isPending}
            onClick={() => refreshMutation.mutate()}
          >
            {refreshMutation.isPending ? "Syncing…" : "Sync from provider"}
          </Button>
        </div>
        {dailyQuery.isLoading ? <LoadingState label="Loading daily" /> : null}
        {dailyQuery.isError ? (
          <ErrorState
            title="Daily puzzle unavailable"
            message={
              dailyQuery.error instanceof Error
                ? dailyQuery.error.message
                : "Not in local catalog yet — sync from provider"
            }
            onRetry={() => void dailyQuery.refetch()}
          />
        ) : null}
        {refreshMutation.isError ? (
          <ErrorState
            title="Sync failed"
            message={
              refreshMutation.error instanceof Error
                ? refreshMutation.error.message
                : "Provider refresh failed"
            }
            onRetry={() => refreshMutation.mutate()}
          />
        ) : null}
        {dailyQuery.data ? (
          <div className="flex flex-col gap-3 sm:flex-row">
            <ChessBoardPreview fen={dailyQuery.data.starting_fen} size="md" />
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium">
                  Daily · {dailyQuery.data.provider}/{dailyQuery.data.external_id}
                </p>
                <Badge variant={dailyQuery.data.is_stale ? "warning" : "secondary"}>
                  {dailyFreshnessLabel({
                    is_stale: dailyQuery.data.is_stale,
                    freshness: dailyQuery.data.freshness,
                  })}
                </Badge>
              </div>
              {dailyQuery.data.is_stale ? (
                <p className="text-xs text-muted-foreground">
                  Showing {dailyQuery.data.daily_utc ?? "last synced"} (provider offline or not
                  refreshed today)
                </p>
              ) : null}
              {formatDisplayDateTime(dailyQuery.data.retrieved_at) ? (
                <p className="text-xs text-muted-foreground">
                  Last retrieved · {formatDisplayDateTime(dailyQuery.data.retrieved_at)}
                </p>
              ) : null}
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

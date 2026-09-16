import { useState } from "react";
import type { ChessGame, ChessGameSearchParams } from "../../api/chessData";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { FieldHelp } from "../../components/ui/HelpDisclosure";
import { ChessListSkeleton } from "./ChessListSkeleton";
import { IMPORTED_PROVIDER_OPTIONS } from "./constants";
import { GameCard } from "./GameCard";
import { useChessGames } from "./hooks/useChessGames";

const DEFAULT: ChessGameSearchParams = { limit: 20 };

export type ImportedGamesPanelProps = {
  selectedId?: string | null;
  onSelect: (game: ChessGame) => void;
  onView?: (game: ChessGame) => void;
  onAnalyze?: (game: ChessGame) => void;
  onCreateVideo?: (game: ChessGame) => void;
  creating?: boolean;
  analyzingId?: string | null;
};

export function ImportedGamesPanel({
  selectedId = null,
  onSelect,
  onView,
  onAnalyze,
  onCreateVideo,
  creating = false,
  analyzingId = null,
}: ImportedGamesPanelProps) {
  const [provider, setProvider] = useState("");
  const [applied, setApplied] = useState<ChessGameSearchParams>(DEFAULT);
  const query = useChessGames(applied);

  return (
    <div className="space-y-4">
      <Card className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
        <label className="min-w-0 flex-1 space-y-1 text-sm">
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            Import source
            <FieldHelp content="Filter catalog games by how they were ingested (archive, masters API, etc.)." />
          </span>
          <select
            className="h-11 w-full rounded-md border border-border bg-background px-3"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            {IMPORTED_PROVIDER_OPTIONS.map((option) => (
              <option key={option.value || "any"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <Button
          type="button"
          onClick={() =>
            setApplied({
              limit: 20,
              provider: provider || undefined,
            })
          }
        >
          Load imported
        </Button>
      </Card>
      {query.isLoading ? <ChessListSkeleton label="Loading imported games" /> : null}
      {query.isError ? (
        <ErrorState
          title="Could not load imported games"
          message={query.error instanceof Error ? query.error.message : "Request failed"}
          onRetry={() => void query.refetch()}
        />
      ) : null}
      <div className="grid gap-2">
        {(query.data?.items ?? []).map((game) => (
          <GameCard
            key={game.id}
            game={game}
            selected={selectedId === game.id}
            onSelect={onSelect}
            onView={onView}
            onAnalyze={onAnalyze}
            onCreateVideo={onCreateVideo}
            creating={creating}
            analyzing={analyzingId === game.id}
          />
        ))}
        {query.isSuccess && (query.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="No imported games"
            description="Run a PGN archive or provider import, then refresh this list to select content."
          />
        ) : null}
      </div>
    </div>
  );
}

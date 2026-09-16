import { useState } from "react";
import type { ChessGame, ChessGameSearchParams } from "../../api/chessData";
import { Card } from "../../components/ui/card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SectionHelp } from "../../components/ui/HelpDisclosure";
import { ChessListSkeleton } from "./ChessListSkeleton";
import { GameCard } from "./GameCard";
import { GameFilters } from "./GameFilters";
import { useChessGames } from "./hooks/useChessGames";

const DEFAULT: ChessGameSearchParams = { limit: 20 };

export type GameSearchPanelProps = {
  selectedId?: string | null;
  onSelect: (game: ChessGame) => void;
  onView?: (game: ChessGame) => void;
  onAnalyze?: (game: ChessGame) => void;
  onCreateVideo?: (game: ChessGame) => void;
  creating?: boolean;
  analyzingId?: string | null;
};

export function GameSearchPanel({
  selectedId = null,
  onSelect,
  onView,
  onAnalyze,
  onCreateVideo,
  creating = false,
  analyzingId = null,
}: GameSearchPanelProps) {
  const [draft, setDraft] = useState<ChessGameSearchParams>(DEFAULT);
  const [applied, setApplied] = useState<ChessGameSearchParams>(DEFAULT);
  const query = useChessGames(applied);

  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-4">
        <div className="space-y-1">
          <h2 className="text-base font-medium text-foreground">Search games</h2>
          <p className="text-sm text-muted-foreground">
            Find historical matches worth turning into analysis or video content.
          </p>
        </div>
        <SectionHelp summary="How search works">
          Filter by player, era, and opening. Results are content candidates — open a game to
          review moves, run Stockfish, or start a video job. This is not a raw database browser.
        </SectionHelp>
        <GameFilters value={draft} onChange={setDraft} onSubmit={() => setApplied({ ...draft })} />
      </Card>
      {query.isLoading ? <ChessListSkeleton label="Searching catalog" /> : null}
      {query.isError ? (
        <ErrorState
          title="Could not search games"
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
            title="No matching games"
            description="No games matched these filters. Try a broader player name, year range, or clear Famous only."
          />
        ) : null}
      </div>
    </div>
  );
}

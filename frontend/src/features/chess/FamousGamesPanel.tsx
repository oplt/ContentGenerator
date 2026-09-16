import type { ChessGame } from "../../api/chessData";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { ChessListSkeleton } from "./ChessListSkeleton";
import { GameCard } from "./GameCard";
import { useFamousChessGames } from "./hooks/useChessGames";

export type FamousGamesPanelProps = {
  selectedId?: string | null;
  onSelect: (game: ChessGame) => void;
  onView?: (game: ChessGame) => void;
  onAnalyze?: (game: ChessGame) => void;
  onCreateVideo?: (game: ChessGame) => void;
  creating?: boolean;
  analyzingId?: string | null;
};

export function FamousGamesPanel({
  selectedId = null,
  onSelect,
  onView,
  onAnalyze,
  onCreateVideo,
  creating = false,
  analyzingId = null,
}: FamousGamesPanelProps) {
  const query = useFamousChessGames(24);

  if (query.isLoading) return <ChessListSkeleton label="Loading famous games" />;
  if (query.isError) {
    return (
      <ErrorState
        title="Could not load famous games"
        message={query.error instanceof Error ? query.error.message : "Request failed"}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const items = query.data?.items ?? [];
  if (!items.length) {
    return (
      <EmptyState
        title="No famous games yet"
        description="Apply the famous catalog or import PGN archives, then return here to pick classics for content."
      />
    );
  }

  return (
    <div className="grid gap-2">
      {items.map((game) => (
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
    </div>
  );
}

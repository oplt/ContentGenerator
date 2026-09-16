import { useState } from "react";
import type { ChessGame } from "../../api/chessData";
import { LoadingState } from "../../components/ui/LoadingState";
import { AnalyzeGameAction } from "./AnalyzeGameAction";
import { ChessBoardPreview } from "./ChessBoardPreview";
import { ContentOpportunityPanel } from "./ContentOpportunityPanel";
import { CreateVideoAction } from "./CreateVideoAction";
import { MoveViewer } from "./MoveViewer";
import { ProvenancePanel } from "./ProvenancePanel";
import { useChessGameMoves } from "./hooks/useChessGames";

export type GameDetailsProps = {
  game: ChessGame;
  onCreateVideo?: (game: ChessGame) => void;
  onUseInCreator?: (game: ChessGame) => void;
  creating?: boolean;
};

export function GameDetails({
  game,
  onCreateVideo,
  onUseInCreator,
  creating = false,
}: GameDetailsProps) {
  const movesQuery = useChessGameMoves(game.id);
  const [activePly, setActivePly] = useState<number | null>(null);
  const activeMove = movesQuery.data?.find((move) => move.ply === activePly);
  const fen = activeMove?.fen_after ?? game.starting_fen;
  const title =
    game.famous_title ||
    (game.white_player && game.black_player
      ? `${game.white_player} vs ${game.black_player}`
      : `Game ${game.id.slice(0, 8)}`);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-medium text-foreground">{title}</h3>
        <p className="text-sm text-muted-foreground">
          {[game.event, game.game_date ?? game.year, game.result, game.opening, game.eco]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>
      <div className="flex flex-col gap-4 sm:flex-row">
        <ChessBoardPreview fen={fen} size="md" />
        <div className="min-w-0 flex-1 space-y-3">
          {movesQuery.isLoading ? (
            <LoadingState label="Loading moves" />
          ) : (
            <MoveViewer
              moves={movesQuery.data ?? []}
              activePly={activePly}
              onSelectPly={setActivePly}
            />
          )}
          <CreateVideoAction
            onCreateVideo={onCreateVideo ? () => onCreateVideo(game) : undefined}
            onUseInCreator={onUseInCreator ? () => onUseInCreator(game) : undefined}
            creating={creating}
          />
          <ContentOpportunityPanel gameId={game.id} />
          <ProvenancePanel gameId={game.id} />
          <AnalyzeGameAction gameId={game.id} activePly={activePly} />
        </div>
      </div>
    </div>
  );
}

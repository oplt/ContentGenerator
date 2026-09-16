import type { ChessGame } from "../../api/chessData";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { ChessBoardPreview } from "./ChessBoardPreview";

export type GameCardProps = {
  game: ChessGame;
  selected?: boolean;
  onSelect?: (game: ChessGame) => void;
  onView?: (game: ChessGame) => void;
  onAnalyze?: (game: ChessGame) => void;
  onCreateVideo?: (game: ChessGame) => void;
  creating?: boolean;
  analyzing?: boolean;
};

export function gameCardTitle(game: ChessGame): string {
  if (game.famous_title) return game.famous_title;
  if (game.white_player && game.black_player) {
    return `${game.white_player} vs ${game.black_player}`;
  }
  return `Game ${game.id.slice(0, 8)}`;
}

export function gameCardMeta(game: ChessGame): string {
  const place = game.site || game.event;
  const round = game.round ? (game.round.match(/^\d+$/) ? `Game ${game.round}` : game.round) : null;
  return [place, game.year, round].filter(Boolean).join(" · ") || "—";
}

export function gameCardOpening(game: ChessGame): string | null {
  if (game.opening) return game.opening;
  if (game.eco) return game.eco;
  return null;
}

export function GameCard({
  game,
  selected = false,
  onSelect,
  onView,
  onAnalyze,
  onCreateVideo,
  creating = false,
  analyzing = false,
}: GameCardProps) {
  const title = gameCardTitle(game);
  const opening = gameCardOpening(game);
  const showActions = Boolean(onView || onAnalyze || onCreateVideo);

  return (
    <Card
      className={`flex flex-col gap-3 p-3 transition-colors ${
        selected ? "border-primary bg-primary/5" : "hover:bg-muted/30"
      }`}
    >
      <button
        type="button"
        onClick={() => onSelect?.(game)}
        className="flex w-full gap-3 text-left"
        aria-pressed={selected}
      >
        <ChessBoardPreview fen={game.starting_fen} />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-foreground">{title}</p>
            {game.is_famous ? (
              <Badge variant="warning" className="shrink-0">
                ★ Famous
              </Badge>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground">{gameCardMeta(game)}</p>
          {opening ? <p className="truncate text-xs text-muted-foreground">{opening}</p> : null}
        </div>
      </button>
      {showActions ? (
        <div className="flex flex-wrap gap-2 border-t border-border pt-2">
          {onView ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => onView(game)}
            >
              View game
            </Button>
          ) : null}
          {onAnalyze ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={analyzing}
              onClick={() => onAnalyze(game)}
            >
              {analyzing ? "Analyzing…" : "Analyze"}
            </Button>
          ) : null}
          {onCreateVideo ? (
            <Button
              type="button"
              size="sm"
              disabled={creating}
              onClick={() => onCreateVideo(game)}
            >
              {creating ? "Starting…" : "Create video"}
            </Button>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

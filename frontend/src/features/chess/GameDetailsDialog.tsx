import type { ChessGame } from "../../api/chessData";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "../../components/ui/dialog";
import { GameDetails } from "./GameDetails";

export type GameDetailsDialogProps = {
  game: ChessGame | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreateVideo?: (game: ChessGame) => void;
  onUseInCreator?: (game: ChessGame) => void;
  creating?: boolean;
};

/** Mobile / compact view for catalog selection (Phase 29 drawers/dialogs). */
export function GameDetailsDialog({
  game,
  open,
  onOpenChange,
  onCreateVideo,
  onUseInCreator,
  creating = false,
}: GameDetailsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        {game ? (
          <>
            <DialogTitle className="pr-8">
              {game.famous_title ||
                (game.white_player && game.black_player
                  ? `${game.white_player} vs ${game.black_player}`
                  : "Game details")}
            </DialogTitle>
            <DialogDescription className="sr-only">
              Review moves, analyze, or hand off this game to video creation.
            </DialogDescription>
            <GameDetails
              game={game}
              creating={creating}
              onCreateVideo={onCreateVideo}
              onUseInCreator={onUseInCreator}
            />
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

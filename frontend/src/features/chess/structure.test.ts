/** Phase 28 — chess frontend structure matches the adopted layout. */

import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { CHESS_WORKSPACE_TABS } from "./constants";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "../..");

const REQUIRED = [
  "api/chessData.ts",
  "api/chessVideos.ts",
  "features/chess/GameSearchPanel.tsx",
  "features/chess/FamousGamesPanel.tsx",
  "features/chess/PuzzleBrowserPanel.tsx",
  "features/chess/GameFilters.tsx",
  "features/chess/GameCard.tsx",
  "features/chess/GameDetails.tsx",
  "features/chess/MoveViewer.tsx",
  "features/chess/PuzzleCard.tsx",
  "features/chess/PuzzleViewer.tsx",
  "features/chess/CreateVideoAction.tsx",
  "features/chess/ChessListSkeleton.tsx",
  "features/chess/GameDetailsDialog.tsx",
  "features/chess/GamesWorkspace.tsx",
  "features/chess/PuzzlesWorkspace.tsx",
  "features/chess/video/CreateVideoTab.tsx",
  "pages/ChessVideoPage.tsx",
] as const;

describe("chess frontend structure (Phase 28)", () => {
  it("keeps suggested feature/api/page files", () => {
    const missing = REQUIRED.filter((rel) => !existsSync(path.join(SRC, rel)));
    expect(missing).toEqual([]);
  });

  it("keeps ChessVideoPage route name (no rename for purity)", () => {
    expect(existsSync(path.join(SRC, "pages/ChessVideoPage.tsx"))).toBe(true);
    expect(existsSync(path.join(SRC, "pages/ChessWorkspacePage.tsx"))).toBe(false);
    expect(CHESS_WORKSPACE_TABS).toEqual([
      "games",
      "puzzles",
      "create",
      "preview",
      "history",
    ]);
  });
});

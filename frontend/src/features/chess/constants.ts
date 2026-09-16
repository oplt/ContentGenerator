export const CHESS_WORKSPACE_TABS = [
  "games",
  "puzzles",
  "create",
  "preview",
  "history",
] as const;
export type ChessWorkspaceTab = (typeof CHESS_WORKSPACE_TABS)[number];

export const CHESS_GAMES_TABS = ["search", "famous", "imported"] as const;
export type ChessGamesTab = (typeof CHESS_GAMES_TABS)[number];

export const CHESS_PUZZLES_TABS = ["browse", "daily"] as const;
export type ChessPuzzlesTab = (typeof CHESS_PUZZLES_TABS)[number];

/** @deprecated Prefer CHESS_GAMES_TABS + CHESS_PUZZLES_TABS */
export const CHESS_CATALOG_TABS = ["search", "famous", "puzzles"] as const;
export type ChessCatalogTab = (typeof CHESS_CATALOG_TABS)[number];

export const RESULT_OPTIONS = ["1-0", "0-1", "1/2-1/2"] as const;

export const IMPORTED_PROVIDER_OPTIONS = [
  { value: "", label: "Any provider" },
  { value: "pgn_archive", label: "PGN archive" },
  { value: "lichess_masters", label: "Lichess masters" },
  { value: "chesscom", label: "Chess.com" },
  { value: "manual", label: "Manual" },
] as const;

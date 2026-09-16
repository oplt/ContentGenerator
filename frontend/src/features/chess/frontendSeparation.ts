/**
 * §23 — frontend chess separation contract.
 *
 * Keep `api/chessData.ts` + `api/chessVideos.ts` + `features/chess/*`.
 * Do NOT add provider clients (`lichessApi.ts`, `chessHybrid.ts`, …).
 * All chess HTTP goes to the SignalForge API (backend owns providers).
 */

/** Canonical API modules — catalog vs render jobs. */
export const ALLOWED_CHESS_API_MODULES = [
  "api/chessData.ts",
  "api/chessVideos.ts",
] as const;

/** Prompt-forbidden parallel client modules. */
export const FORBIDDEN_CHESS_API_MODULES = [
  "api/chessHybrid.ts",
  "api/historicalChessApi.ts",
  "api/lichessApi.ts",
  "api/chessComApi.ts",
  "api/lichess.ts",
  "api/chesscom.ts",
] as const;

/**
 * UI concepts map onto existing feature surfaces — do not invent parallel trees
 * or expand ChessVideoPage into a monolith.
 */
export const UI_CONCEPT_TO_SURFACE = {
  "Historical / Famous": "FamousGamesPanel + GamesWorkspace famous tab",
  Recent: "GameSearchPanel / ImportedGamesPanel (catalog filters)",
  Puzzles: "PuzzlesWorkspace (browse + daily)",
  "Content Opportunities": "ContentOpportunityPanel",
  "Create Video": "video/CreateVideoTab + CreateVideoAction",
  Analysis: "AnalyzeGameAction",
} as const;

/** Host substrings that must never appear in FE chess api/feature sources. */
export const FORBIDDEN_PROVIDER_HOST_FRAGMENTS = [
  "lichess.org",
  "explorer.lichess",
  "api.chess.com",
  "chess.com/api",
] as const;

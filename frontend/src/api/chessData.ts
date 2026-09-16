/** Provider-independent chess catalog API (games/puzzle search). */

import { apiFetch, type ApiFetchOptions } from "./client";
import type { ChessVideoCreateRequest, ChessVideoJob } from "./chessVideos";

export type ChessGame = {
  id: string;
  tenant_id: string;
  white_player?: string | null;
  black_player?: string | null;
  white_rating?: number | null;
  black_rating?: number | null;
  event?: string | null;
  site?: string | null;
  round?: string | null;
  game_date?: string | null;
  year?: number | null;
  result?: string | null;
  eco?: string | null;
  opening?: string | null;
  variation?: string | null;
  starting_fen: string;
  final_fen?: string | null;
  normalized_pgn: string;
  move_count: number;
  source_provider?: string | null;
  source_external_id?: string | null;
  source_url?: string | null;
  is_famous: boolean;
  famous_title?: string | null;
  historical_tags: string[];
  created_at: string;
  updated_at: string;
};

export type ChessPuzzle = {
  id: string;
  tenant_id: string;
  external_id: string;
  provider: string;
  starting_fen: string;
  solution_moves_uci: string[];
  solution_moves_san: string[];
  rating?: number | null;
  popularity?: number | null;
  play_count?: number | null;
  themes: string[];
  opening_tags: string[];
  source_game_url?: string | null;
  created_at: string;
  updated_at: string;
};

export type ChessMove = {
  ply: number;
  move_number: number;
  side: string;
  san: string;
  uci: string;
  fen_before: string;
  fen_after: string;
};

export type ChessGamePage = {
  items: ChessGame[];
  next_cursor?: string | null;
  has_more: boolean;
};

export type ChessPuzzlePage = {
  items: ChessPuzzle[];
  next_cursor?: string | null;
  has_more: boolean;
};

export type ChessGameSearchParams = {
  player?: string;
  white_player?: string;
  black_player?: string;
  year_from?: number;
  year_to?: number;
  event?: string;
  result?: string;
  opening?: string;
  eco?: string;
  famous_only?: boolean;
  provider?: string;
  min_rating?: number;
  max_rating?: number;
  tag?: string;
  limit?: number;
  cursor?: string | null;
};

export type ChessPuzzleSearchParams = {
  min_rating?: number;
  max_rating?: number;
  theme?: string;
  opening?: string;
  min_popularity?: number;
  provider?: string;
  limit?: number;
  cursor?: string | null;
};

export type ChessGameVideoOptions = Omit<ChessVideoCreateRequest, "source_text" | "chess_game_id">;

function toQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    qs.set(key, String(value));
  }
  const encoded = qs.toString();
  return encoded ? `?${encoded}` : "";
}

export function searchChessGames(params: ChessGameSearchParams = {}, init?: ApiFetchOptions) {
  return apiFetch<ChessGamePage>(`/chess/games${toQuery(params)}`, init);
}

export function listFamousChessGames(
  params: { limit?: number; cursor?: string | null } = {},
  init?: ApiFetchOptions,
) {
  return apiFetch<ChessGamePage>(`/chess/games/famous${toQuery(params)}`, init);
}

export function getChessGame(gameId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessGame>(`/chess/games/${gameId}`, init);
}

export function getChessGameMoves(gameId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessMove[]>(`/chess/games/${gameId}/moves`, init);
}

export function importChessGame(
  payload: {
    pgn: string;
    provider?: string;
    external_id?: string;
    source_url?: string;
    source_name?: string;
  },
  init?: ApiFetchOptions,
) {
  return apiFetch<{ game: ChessGame; created_game: boolean; created_source: boolean }>(
    "/chess/games/import",
    {
      ...init,
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function createChessVideoFromGame(
  gameId: string,
  payload: ChessGameVideoOptions = {},
  init?: ApiFetchOptions,
) {
  return apiFetch<ChessVideoJob>(`/chess/games/${gameId}/video`, {
    ...init,
    method: "POST",
    timeoutMs: init?.timeoutMs ?? 120_000,
    body: JSON.stringify(payload),
  });
}

export type ChessPositionAnalysis = {
  id: string;
  ply: number;
  fen: string;
  evaluation_cp?: number | null;
  mate_in?: number | null;
  evaluation_before_cp?: number | null;
  mate_before?: number | null;
  evaluation_after_cp?: number | null;
  mate_after?: number | null;
  evaluation_delta?: number | null;
  best_move_uci?: string | null;
  best_move_san?: string | null;
  played_move_uci: string;
  played_move_san: string;
  depth: number;
  nodes: number;
  engine_name?: string | null;
  engine_version?: string | null;
};

export type ChessCriticalMoment = {
  id: string;
  ply: number;
  classification: string;
  confidence: number;
  detection_method: string;
  engine_facts: Record<string, unknown>;
  heuristic_summary: string;
  editorial_description?: string | null;
};

export type ChessTacticalPattern = {
  id: string;
  ply: number;
  pattern: string;
  confidence: number;
  detection_method: string;
  facts: Record<string, unknown>;
  summary: string;
};

export type ChessContentOpportunityScore = {
  id?: string | null;
  chess_game_id: string;
  analysis_job_id?: string | null;
  score: number;
  components: Record<string, number>;
  reasons: Record<string, string[]>;
  formula_version: string;
  created_at?: string | null;
  updated_at?: string | null;
  persisted?: boolean;
};

export type ChessAnalysisJob = {
  id: string;
  tenant_id: string;
  chess_game_id: string;
  status: string;
  progress: number;
  error_message?: string | null;
  depth?: number | null;
  time_limit_seconds?: number | null;
  hash_mb: number;
  threads: number;
  engine_name?: string | null;
  engine_version?: string | null;
  analysis_settings: Record<string, unknown>;
  ply_count: number;
  created_at: string;
  updated_at: string;
  positions: ChessPositionAnalysis[];
  critical_moments: ChessCriticalMoment[];
  tactical_patterns: ChessTacticalPattern[];
  content_opportunity?: ChessContentOpportunityScore | null;
};

export type ChessAnalysisOptions = {
  depth?: number;
  time_limit_seconds?: number;
};

export function enqueueChessGameAnalysis(
  gameId: string,
  payload: ChessAnalysisOptions = {},
  init?: ApiFetchOptions,
) {
  return apiFetch<ChessAnalysisJob>(`/chess/games/${gameId}/analyze`, {
    ...init,
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getChessGameAnalysis(gameId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessAnalysisJob>(`/chess/games/${gameId}/analysis`, init);
}

export function getChessAnalysisJob(jobId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessAnalysisJob>(`/chess/analysis/${jobId}`, init);
}

export function getChessGameContentScore(gameId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessContentOpportunityScore>(`/chess/games/${gameId}/content-score`, init);
}

export type ChessSourceRecord = {
  id?: string | null;
  provider: string;
  external_id?: string | null;
  source_url?: string | null;
  source_name?: string | null;
  source_metadata?: Record<string, unknown>;
  import_batch_id?: string | null;
  license_note?: string | null;
  retrieved_at?: string | null;
  is_primary?: boolean;
};

export type ChessGameProvenance = {
  entity_type: "chess_game";
  chess_game_id: string;
  normalized_pgn: string;
  content_hash: string;
  game_fingerprint: string;
  primary_source?: ChessSourceRecord | null;
  sources: ChessSourceRecord[];
  evidence_note: string;
};

export type ChessPuzzleProvenance = {
  entity_type: "chess_puzzle";
  chess_puzzle_id: string;
  provider: string;
  external_id: string;
  starting_fen: string;
  solution_moves_uci: string[];
  source_game_id?: string | null;
  source_game_url?: string | null;
  source_metadata?: Record<string, unknown>;
  import_batch_id?: string | null;
  license_note?: string | null;
  retrieved_at?: string | null;
  content_hash: string;
  puzzle_fingerprint: string;
  evidence_note: string;
};

export function getChessGameProvenance(gameId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessGameProvenance>(`/chess/games/${gameId}/provenance`, init);
}

export function getChessPuzzleProvenance(puzzleId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessPuzzleProvenance>(`/chess/puzzles/${puzzleId}/provenance`, init);
}

export function searchChessPuzzles(params: ChessPuzzleSearchParams = {}, init?: ApiFetchOptions) {
  return apiFetch<ChessPuzzlePage>(`/chess/puzzles${toQuery(params)}`, init);
}

export function getChessPuzzle(puzzleId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessPuzzle>(`/chess/puzzles/${puzzleId}`, init);
}

export function getDailyChessPuzzle(init?: ApiFetchOptions) {
  return apiFetch<ChessPuzzle>("/chess/puzzles/daily", {
    ...init,
    method: "GET",
    timeoutMs: init?.timeoutMs ?? 60_000,
  });
}

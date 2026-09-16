/** Chess video render jobs API — SignalForge only (§23). No provider clients here. */

import { apiFetch, type ApiFetchOptions } from "./client";

export type ChessVideoStatus =
  | "queued"
  | "validating"
  | "preparing"
  | "rendering"
  | "encoding"
  | "uploading"
  | "completed"
  | "failed"
  | "cancelled";

export type ChessRenderPreset =
  | "economy_vertical"
  | "social_vertical"
  | "square"
  | "horizontal";

export type ChessBoardTheme =
  | "classic_wood"
  | "tournament_green"
  | "midnight_blue"
  | "slate"
  | "high_contrast";

export type ChessInputFormat = "pgn" | "san" | "uci" | "auto";

export type ChessVideoCreateRequest = {
  source_text?: string;
  chess_game_id?: string;
  input_format?: ChessInputFormat;
  orientation?: "white" | "black";
  render_preset?: ChessRenderPreset;
  board_theme?: ChessBoardTheme;
  seconds_per_move?: number;
  include_coordinates?: boolean;
  include_move_text?: boolean;
  title?: string | null;
  subtitle?: string | null;
};

export type ChessVideoValidation = {
  valid: boolean;
  input_format: string;
  detected_format?: string | null;
  normalized_pgn?: string | null;
  white_player?: string | null;
  black_player?: string | null;
  event?: string | null;
  game_date?: string | null;
  result?: string | null;
  starting_fen?: string | null;
  move_count: number;
  errors: string[];
};

export type ChessVideoJob = {
  id: string;
  tenant_id: string;
  created_by_user_id?: string | null;
  status: ChessVideoStatus | string;
  stage: string;
  progress: number;
  input_format: string;
  chess_game_id?: string | null;
  source_hash?: string | null;
  white_player?: string | null;
  black_player?: string | null;
  event?: string | null;
  game_date?: string | null;
  result?: string | null;
  starting_fen?: string | null;
  move_count: number;
  orientation: string;
  render_preset: string;
  board_theme?: string;
  seconds_per_move: number;
  include_coordinates: boolean;
  include_move_text: boolean;
  title?: string | null;
  subtitle?: string | null;
  renderer_version?: string | null;
  render_fingerprint?: string | null;
  video_public_url?: string | null;
  thumbnail_public_url?: string | null;
  duration_seconds?: number | null;
  width?: number | null;
  height?: number | null;
  file_size_bytes?: number | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
};

export function validateChessGame(
  payload: { source_text: string; input_format?: ChessInputFormat },
  init?: ApiFetchOptions,
) {
  const source_text = payload.source_text.trim();
  const body = JSON.stringify({
    source_text,
    input_format: payload.input_format ?? "auto",
  });
  return apiFetch<ChessVideoValidation>("/chess-videos/validate", {
    ...init,
    method: "POST",
    body,
  });
}

export function createChessVideo(payload: ChessVideoCreateRequest, init?: ApiFetchOptions) {
  const body: Record<string, unknown> = {
    ...payload,
    title: payload.title?.trim() || null,
    subtitle: payload.subtitle?.trim() || null,
  };
  if (payload.chess_game_id) {
    body.chess_game_id = payload.chess_game_id;
    delete body.source_text;
  } else {
    body.source_text = (payload.source_text ?? "").trim();
  }
  return apiFetch<ChessVideoJob>("/chess-videos", {
    ...init,
    method: "POST",
    // Large PGNs can take >30s to parse + persist.
    timeoutMs: init?.timeoutMs ?? 120_000,
    body: JSON.stringify(body),
  });
}

export function getChessVideoJobs(limit = 50, init?: ApiFetchOptions) {
  return apiFetch<ChessVideoJob[]>(`/chess-videos?limit=${limit}`, init);
}

export function getChessVideoJob(jobId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessVideoJob>(`/chess-videos/${jobId}`, init);
}

export type ChessVideoProvenance = {
  entity_type: "chess_video";
  chess_video_job_id: string;
  chess_game_id?: string | null;
  normalized_pgn?: string | null;
  source_hash?: string | null;
  game?: unknown;
  evidence_note: string;
};

export function getChessVideoProvenance(jobId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessVideoProvenance>(`/chess-videos/${jobId}/provenance`, init);
}

export function retryChessVideoJob(jobId: string, init?: ApiFetchOptions) {
  return apiFetch<ChessVideoJob>(`/chess-videos/${jobId}/retry`, {
    method: "POST",
    ...init,
  });
}

export function deleteChessVideoJob(jobId: string, init?: ApiFetchOptions) {
  return apiFetch<void>(`/chess-videos/${jobId}`, {
    method: "DELETE",
    ...init,
  });
}

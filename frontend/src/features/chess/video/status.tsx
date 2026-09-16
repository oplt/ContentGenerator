import type { ChessBoardTheme, ChessRenderPreset, ChessVideoJob } from "../../../api/chessVideos";
import { AlertCircle, CheckCircle2, Film, RefreshCw } from "lucide-react";
import { Button } from "../../../components/ui/button";


export const PRESETS: { value: ChessRenderPreset; label: string }[] = [
  { value: "economy_vertical", label: "Economy Vertical" },
  { value: "social_vertical", label: "Social Vertical" },
  { value: "square", label: "Square" },
  { value: "horizontal", label: "Horizontal" },
];

export const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

export const BOARD_THEMES: { value: ChessBoardTheme; label: string; light: string; dark: string }[] = [
  { value: "classic_wood", label: "Classic wood", light: "#f0d9b5", dark: "#b58863" },
  { value: "tournament_green", label: "Tournament green", light: "#ebecd0", dark: "#779556" },
  { value: "midnight_blue", label: "Midnight blue", light: "#dee3eb", dark: "#3e6ae1" },
  { value: "slate", label: "Slate", light: "#e8eaed", dark: "#5c5e62" },
  { value: "high_contrast", label: "High contrast", light: "#ffffff", dark: "#282828" },
];


export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return minutes ? `${minutes}:${String(remaining).padStart(2, "0")}` : `${remaining}s`;
}

export function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function presetLabel(value: string | null | undefined): string {
  return PRESETS.find((preset) => preset.value === value)?.label ?? value ?? "—";
}

export function themeLabel(value: string | null | undefined): string {
  return BOARD_THEMES.find((theme) => theme.value === value)?.label ?? value ?? "Classic wood";
}

export function gameTitle(job: ChessVideoJob): string {
  if (job.title) return job.title;
  if (job.white_player && job.black_player) return `${job.white_player} vs ${job.black_player}`;
  return `Job ${job.id.slice(0, 8)}`;
}

export function statusLabel(status: string): string {
  if (status === "completed") return "Completed";
  if (status === "failed") return "Failed";
  if (status === "queued") return "Queued";
  if (status === "cancelled") return "Cancelled";
  return "Generating";
}

export function JobStatusBadge({ status }: { status: string }) {
  const label = statusLabel(status);
  return (
    <span className="inline-flex min-h-7 items-center rounded-full border border-border bg-muted/40 px-2.5 text-xs font-medium capitalize text-muted-foreground">
      {label}
    </span>
  );
}

export function GenerationStatus({
  job,
  onViewVideo,
  onRetry,
  retrying,
}: {
  job: ChessVideoJob;
  onViewVideo: () => void;
  onRetry: () => void;
  retrying: boolean;
}) {
  const pct = Math.round(Math.min(1, Math.max(0, job.progress)) * 100);
  const isComplete = job.status === "completed";
  const isFailed = job.status === "failed";

  return (
    <div className="rounded-md border border-border bg-muted/25 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="flex items-center gap-2 text-sm font-medium text-foreground">
            {isComplete ? <CheckCircle2 className="size-4 text-primary" /> : null}
            {isFailed ? <AlertCircle className="size-4 text-destructive" /> : null}
            {isComplete ? "Video ready" : isFailed ? "Generation failed" : "Generating video"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {gameTitle(job)}
            {job.move_count ? ` · ${job.move_count} moves` : ""}
          </p>
          {job.error_message ? (
            <p className="mt-2 text-sm text-destructive">{job.error_message}</p>
          ) : null}
        </div>
        <span className="text-sm tabular-nums text-muted-foreground">{pct}%</span>
      </div>
      <div
        className="mt-3 h-2 overflow-hidden rounded bg-muted"
        role="progressbar"
        aria-label="Video generation progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {isComplete && job.video_public_url ? (
          <Button type="button" size="sm" onClick={onViewVideo}>
            <Film className="size-4" />
            View video
          </Button>
        ) : null}
        {isFailed ? (
          <Button type="button" variant="secondary" size="sm" disabled={retrying} onClick={onRetry}>
            <RefreshCw className="size-4" />
            Retry
          </Button>
        ) : null}
      </div>
    </div>
  );
}

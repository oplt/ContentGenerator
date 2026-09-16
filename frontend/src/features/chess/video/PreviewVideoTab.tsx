import { AlertCircle, Download, Film, RefreshCw } from "lucide-react";
import type { ChessVideoJob } from "../../../api/chessVideos";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import {
  formatBytes,
  formatDate,
  formatDuration,
  gameTitle,
  presetLabel,
  themeLabel,
  GenerationStatus,
} from "./status";

export function PreviewVideoTab({
  activeJob,
  onEditSettings,
  onRegenerate,
  regenerating,
  onRetry,
  retrying,
}: {
  activeJob: ChessVideoJob | undefined;
  onEditSettings: () => void;
  onRegenerate: () => void;
  regenerating: boolean;
  onRetry: () => void;
  retrying: boolean;
}) {
  if (!activeJob) {
    return (
      <Card className="flex min-h-[360px] flex-col items-center justify-center gap-3 p-6 text-center">
        <Film className="size-8 text-muted-foreground" />
        <div>
          <h2 className="text-lg font-medium text-foreground">Video preview</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Generate a video first to preview and download it.
          </p>
        </div>
        <Button type="button" onClick={onEditSettings}>
          Go to Create
        </Button>
      </Card>
    );
  }

  const hasVideo = Boolean(activeJob.status === "completed" && activeJob.video_public_url);

  return (
    <Card className="p-4 sm:p-6">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-h-[360px] items-center justify-center rounded-md bg-[#111315] p-4">
          {hasVideo ? (
            <video
              className="max-h-[min(70vh,760px)] w-auto max-w-full rounded bg-black"
              controls
              poster={activeJob.thumbnail_public_url ?? undefined}
              src={activeJob.video_public_url ?? undefined}
            />
          ) : activeJob.status === "failed" ? (
            <div className="max-w-sm text-center text-sm text-muted-foreground">
              <AlertCircle className="mx-auto mb-3 size-8 text-destructive" />
              <p className="font-medium text-background">Preview unavailable</p>
              <p className="mt-1">The render failed before a video was created.</p>
            </div>
          ) : (
            <div className="max-w-sm text-center text-sm text-muted-foreground">
              <Film className="mx-auto mb-3 size-8" />
              <p className="font-medium text-background">Preview loading</p>
              <p className="mt-1">The video will appear here when rendering completes.</p>
            </div>
          )}
        </div>

        <aside className="space-y-5">
          <div>
            <h2 className="text-lg font-medium text-foreground">Preview &amp; Export</h2>
            <p className="mt-1 text-sm text-muted-foreground">{gameTitle(activeJob)}</p>
          </div>

          <VideoDetails job={activeJob} />

          {!hasVideo ? (
            <GenerationStatus
              job={activeJob}
              onViewVideo={() => undefined}
              onRetry={onRetry}
              retrying={retrying}
            />
          ) : null}

          <div className="grid gap-2">
            {hasVideo ? (
              <Button asChild variant="primary">
                <a href={activeJob.video_public_url!} download>
                  <Download className="size-4" />
                  Download Video
                </a>
              </Button>
            ) : null}
            <Button type="button" variant="secondary" onClick={onEditSettings}>
              Edit Settings
            </Button>
            {activeJob.status !== "failed" ? (
              <Button type="button" variant="ghost" disabled={regenerating} onClick={onRegenerate}>
                <RefreshCw className="size-4" />
                Regenerate
              </Button>
            ) : null}
          </div>
        </aside>
      </div>
    </Card>
  );
}

export function VideoDetails({ job }: { job: ChessVideoJob }) {
  return (
    <dl className="space-y-4 text-sm">
      <div>
        <dt className="font-medium text-foreground">Players</dt>
        <dd className="mt-1 text-muted-foreground">
          {job.white_player || "White"} vs {job.black_player || "Black"}
        </dd>
      </div>
      <div>
        <dt className="font-medium text-foreground">Game</dt>
        <dd className="mt-1 text-muted-foreground">
          {job.event || "Untitled game"}
          <br />
          Result: {job.result || "—"}
          <br />
          Moves: {job.move_count}
        </dd>
      </div>
      <div>
        <dt className="font-medium text-foreground">Output</dt>
        <dd className="mt-1 text-muted-foreground">
          {job.width && job.height ? `${job.width}×${job.height}` : "—"}
          <br />
          Duration: {formatDuration(job.duration_seconds)}
          <br />
          Preset: {presetLabel(job.render_preset)}
          <br />
          Theme: {themeLabel(job.board_theme)}
          <br />
          Size: {formatBytes(job.file_size_bytes)}
        </dd>
      </div>
      <div>
        <dt className="font-medium text-foreground">Created</dt>
        <dd className="mt-1 text-muted-foreground">{formatDate(job.created_at)}</dd>
      </div>
    </dl>
  );
}


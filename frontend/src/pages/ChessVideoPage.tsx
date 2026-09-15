import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Download, RefreshCw, Swords, Trash2 } from "lucide-react";
import {
  createChessVideo,
  deleteChessVideoJob,
  getChessVideoJob,
  getChessVideoJobs,
  retryChessVideoJob,
  validateChessGame,
  type ChessInputFormat,
  type ChessRenderPreset,
  type ChessVideoJob,
  type ChessVideoValidation,
} from "../api/chessVideos";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { ErrorState } from "../components/ui/ErrorState";
import { Input } from "../components/ui/input";
import { LoadingState } from "../components/ui/LoadingState";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Textarea } from "../components/ui/textarea";
import { useTenantScope } from "../hooks/useTenantScope";
import { queryKeys } from "../lib/queryKeys";

const PRESETS: { value: ChessRenderPreset; label: string }[] = [
  { value: "economy_vertical", label: "Economy Vertical" },
  { value: "social_vertical", label: "Social Vertical" },
  { value: "square", label: "Square" },
  { value: "horizontal", label: "Horizontal" },
];

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function JobProgress({ job }: { job: ChessVideoJob }) {
  const pct = Math.round(Math.min(1, Math.max(0, job.progress)) * 100);
  const title =
    job.white_player && job.black_player
      ? `${job.white_player} vs ${job.black_player}`
      : job.title || "Chess video";

  return (
    <Card className="space-y-3 p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">
            {job.status === "completed" ? "Finished" : "Rendering Chess Video"}
          </p>
          <h2 className="mt-1 text-lg font-medium">{title}</h2>
          <p className="mt-1 text-sm capitalize text-muted-foreground">
            {job.stage.replaceAll("_", " ")}
            {job.move_count ? ` · ${job.move_count} moves` : ""}
          </p>
        </div>
        <span className="text-sm tabular-nums text-muted-foreground">{pct}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-muted">
        <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </div>
      {job.status === "failed" && job.error_message ? (
        <p className="text-sm text-destructive">{job.error_message}</p>
      ) : null}
    </Card>
  );
}

export default function ChessVideoPage() {
  const { tenantId, enabled } = useTenantScope();
  const queryClient = useQueryClient();
  const [inputMode, setInputMode] = useState<"paste" | "upload">("paste");
  const [sourceText, setSourceText] = useState("");
  const [inputFormat, setInputFormat] = useState<ChessInputFormat>("auto");
  const [renderPreset, setRenderPreset] = useState<ChessRenderPreset>("economy_vertical");
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [secondsPerMove, setSecondsPerMove] = useState(1);
  const [includeCoordinates, setIncludeCoordinates] = useState(true);
  const [includeMoveText, setIncludeMoveText] = useState(true);
  const [title, setTitle] = useState("");
  const [validation, setValidation] = useState<ChessVideoValidation | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const jobsQuery = useQuery({
    queryKey: queryKeys.chessVideos(tenantId ?? "none"),
    queryFn: () => getChessVideoJobs(20),
    enabled,
  });

  const activeJobQuery = useQuery({
    queryKey: queryKeys.chessVideoJob(tenantId ?? "none", activeJobId ?? "none"),
    queryFn: () => getChessVideoJob(activeJobId!),
    enabled: Boolean(enabled && activeJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || TERMINAL.has(status)) return false;
      return 1500;
    },
  });

  const validateMutation = useMutation({
    mutationFn: () => validateChessGame({ source_text: sourceText, input_format: inputFormat }),
    onSuccess: (data) => setValidation(data),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createChessVideo({
        source_text: sourceText,
        input_format: inputFormat,
        orientation,
        render_preset: renderPreset,
        seconds_per_move: Number.isFinite(secondsPerMove) ? secondsPerMove : 1,
        include_coordinates: includeCoordinates,
        include_move_text: includeMoveText,
        title: title.trim() || null,
      }),
    onSuccess: (job) => {
      setActiveJobId(job.id);
      if (tenantId) {
        queryClient.setQueryData(queryKeys.chessVideoJob(tenantId, job.id), job);
        void queryClient.invalidateQueries({ queryKey: queryKeys.chessVideos(tenantId) });
      }
    },
  });

  const retryMutation = useMutation({
    mutationFn: (jobId: string) => retryChessVideoJob(jobId),
    onSuccess: (job) => {
      setActiveJobId(job.id);
      if (tenantId) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.chessVideos(tenantId) });
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (jobId: string) => deleteChessVideoJob(jobId),
    onSuccess: (_data, jobId) => {
      if (activeJobId === jobId) {
        setActiveJobId(null);
      }
      if (tenantId) {
        queryClient.removeQueries({ queryKey: queryKeys.chessVideoJob(tenantId, jobId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.chessVideos(tenantId) });
      }
    },
  });

  const activeJob = activeJobQuery.data;
  const canGenerate = Boolean(validation?.valid && sourceText.trim());

  const recentJobs = useMemo(() => jobsQuery.data ?? [], [jobsQuery.data]);

  async function onUploadFile(file: File | null) {
    if (!file) return;
    const text = await file.text();
    setSourceText(text);
    setInputFormat("pgn");
    setValidation(null);
    setInputMode("upload");
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <Swords className="size-5 text-primary" />
          <h1 className="text-2xl font-normal text-foreground">Chess Video</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Turn PGN, SAN, or UCI moves into a social-ready 2D match video.
        </p>
      </div>

      <Card className="space-y-5 p-6">
        <Tabs value={inputMode} onValueChange={(v) => setInputMode(v as "paste" | "upload")}>
          <TabsList>
            <TabsTrigger value="paste">Paste Moves</TabsTrigger>
            <TabsTrigger value="upload">Upload PGN</TabsTrigger>
          </TabsList>
          <TabsContent value="paste" className="mt-4">
            <Textarea
              rows={10}
              value={sourceText}
              onChange={(e) => {
                setSourceText(e.target.value);
                setValidation(null);
              }}
              placeholder="Paste PGN, SAN, or UCI moves…"
            />
          </TabsContent>
          <TabsContent value="upload" className="mt-4 space-y-3">
            <Input
              type="file"
              accept=".pgn,.txt,text/plain"
              onChange={(e) => void onUploadFile(e.target.files?.[0] ?? null)}
            />
            {sourceText ? (
              <Textarea rows={8} value={sourceText} readOnly className="font-mono text-xs" />
            ) : null}
          </TabsContent>
        </Tabs>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Input format</span>
            <select
              className="w-full rounded-md border border-border bg-background px-3 py-2"
              value={inputFormat}
              onChange={(e) => setInputFormat(e.target.value as ChessInputFormat)}
            >
              <option value="auto">Auto</option>
              <option value="pgn">PGN</option>
              <option value="san">SAN</option>
              <option value="uci">UCI</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Video preset</span>
            <select
              className="w-full rounded-md border border-border bg-background px-3 py-2"
              value={renderPreset}
              onChange={(e) => setRenderPreset(e.target.value as ChessRenderPreset)}
            >
              {PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Board orientation</span>
            <select
              className="w-full rounded-md border border-border bg-background px-3 py-2"
              value={orientation}
              onChange={(e) => setOrientation(e.target.value as "white" | "black")}
            >
              <option value="white">White</option>
              <option value="black">Black</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Seconds per move</span>
            <Input
              type="number"
              min={0.2}
              max={10}
              step={0.1}
              value={secondsPerMove}
              onChange={(e) => setSecondsPerMove(Number(e.target.value) || 1)}
            />
          </label>
        </div>

        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={includeCoordinates}
              onChange={(e) => setIncludeCoordinates(e.target.checked)}
            />
            Show coordinates
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={includeMoveText}
              onChange={(e) => setIncludeMoveText(e.target.checked)}
            />
            Show move notation
          </label>
        </div>

        <label className="block space-y-1 text-sm">
          <span className="text-muted-foreground">Optional title</span>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Match title" />
        </label>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={!sourceText.trim() || validateMutation.isPending}
            onClick={() => validateMutation.mutate()}
          >
            {validateMutation.isPending ? "Validating…" : "Validate Game"}
          </Button>
          <Button
            type="button"
            disabled={!canGenerate || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? "Queuing…" : "Generate Video"}
          </Button>
          {sourceText.trim() && !validation?.valid ? (
            <p className="text-sm text-muted-foreground">Validate the game before generating.</p>
          ) : null}
        </div>

        {validateMutation.isError ? (
          <ErrorState
            message={
              validateMutation.error instanceof Error
                ? validateMutation.error.message
                : "Validation request failed."
            }
            onRetry={() => validateMutation.mutate()}
          />
        ) : null}
        {createMutation.isError ? (
          <ErrorState
            message={
              createMutation.error instanceof Error
                ? createMutation.error.message
                : "Could not queue chess video job."
            }
            onRetry={() => createMutation.mutate()}
          />
        ) : null}

        {validation ? (
          <div className="rounded-md border border-border bg-muted/30 p-4 text-sm">
            {validation.valid ? (
              <dl className="grid gap-1 sm:grid-cols-2">
                <div>White: {validation.white_player || "—"}</div>
                <div>Black: {validation.black_player || "—"}</div>
                <div>Event: {validation.event || "—"}</div>
                <div>Result: {validation.result || "—"}</div>
                <div>Moves: {validation.move_count}</div>
                <div>Detected format: {(validation.detected_format || validation.input_format).toUpperCase()}</div>
              </dl>
            ) : (
              <p className="text-destructive">{validation.errors[0] || "Invalid game."}</p>
            )}
          </div>
        ) : null}
      </Card>

      {activeJob ? (
        <div className="space-y-4">
          <JobProgress job={activeJob} />
          {activeJob.status === "completed" && activeJob.video_public_url ? (
            <Card className="space-y-4 p-6">
              <video
                className="max-h-[70vh] w-full rounded-md bg-black"
                controls
                poster={activeJob.thumbnail_public_url ?? undefined}
                src={activeJob.video_public_url}
              />
              <dl className="grid gap-2 text-sm sm:grid-cols-2">
                <div>Players: {activeJob.white_player || "?"} vs {activeJob.black_player || "?"}</div>
                <div>Result: {activeJob.result || "—"}</div>
                <div>Moves: {activeJob.move_count}</div>
                <div>Duration: {activeJob.duration_seconds?.toFixed(1) ?? "—"}s</div>
                <div>
                  Resolution:{" "}
                  {activeJob.width && activeJob.height
                    ? `${activeJob.width}×${activeJob.height}`
                    : "—"}
                </div>
                <div>Size: {formatBytes(activeJob.file_size_bytes)}</div>
                <div>Preset: {activeJob.render_preset}</div>
                <div>Created: {new Date(activeJob.created_at).toLocaleString()}</div>
              </dl>
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="secondary">
                  <a href={activeJob.video_public_url} download>
                    <Download className="size-4" />
                    Download
                  </a>
                </Button>
              </div>
            </Card>
          ) : null}
          {activeJob.status === "failed" ? (
            <Button
              type="button"
              variant="secondary"
              disabled={retryMutation.isPending}
              onClick={() => retryMutation.mutate(activeJob.id)}
            >
              <RefreshCw className="size-4" />
              Retry
            </Button>
          ) : null}
        </div>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Recent jobs</h2>
        {jobsQuery.isPending ? <LoadingState label="Loading chess videos" /> : null}
        {jobsQuery.isError ? (
          <ErrorState message="Could not load chess video jobs." onRetry={() => void jobsQuery.refetch()} />
        ) : null}
        <div className="space-y-2">
          {recentJobs.map((job) => (
            <div
              key={job.id}
              className="flex items-stretch gap-1 rounded-md border border-border"
            >
              <button
                type="button"
                className="flex min-w-0 flex-1 flex-col gap-1 px-4 py-3 text-left text-sm hover:bg-accent/40 sm:flex-row sm:items-center sm:justify-between"
                onClick={() => setActiveJobId(job.id)}
              >
                <span className="font-medium">
                  {job.title ||
                    (job.white_player && job.black_player
                      ? `${job.white_player} vs ${job.black_player}`
                      : `Job ${job.id.slice(0, 8)}`)}
                </span>
                <span className="flex flex-wrap gap-x-3 gap-y-1 text-muted-foreground">
                  <span className="capitalize">{job.status}</span>
                  <span>{job.move_count} moves</span>
                  {job.duration_seconds != null ? (
                    <span>{Math.round(job.duration_seconds)}s</span>
                  ) : null}
                  {job.width && job.height ? (
                    <span>
                      {job.width}×{job.height}
                    </span>
                  ) : null}
                  <span>{new Date(job.created_at).toLocaleString()}</span>
                </span>
              </button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="m-1 self-center text-muted-foreground hover:text-destructive"
                aria-label={`Delete chess video job ${job.id.slice(0, 8)}`}
                disabled={deleteMutation.isPending && deleteMutation.variables === job.id}
                onClick={() => {
                  if (!window.confirm("Delete this chess video job? This cannot be undone.")) {
                    return;
                  }
                  deleteMutation.mutate(job.id);
                }}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
          {!jobsQuery.isPending && recentJobs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No chess videos yet.</p>
          ) : null}
        </div>
        {deleteMutation.isError ? (
          <ErrorState
            message={
              deleteMutation.error instanceof Error
                ? deleteMutation.error.message
                : "Could not delete chess video job."
            }
          />
        ) : null}
        <Button asChild variant="ghost" size="sm">
          <Link to="/dashboard">Back to dashboard</Link>
        </Button>
      </section>
    </div>
  );
}

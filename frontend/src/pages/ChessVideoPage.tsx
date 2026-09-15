import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Film,
  Play,
  RefreshCw,
  Swords,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  createChessVideo,
  deleteChessVideoJob,
  getChessVideoJob,
  getChessVideoJobs,
  retryChessVideoJob,
  validateChessGame,
  type ChessBoardTheme,
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

const BOARD_THEMES: { value: ChessBoardTheme; label: string; light: string; dark: string }[] = [
  { value: "classic_wood", label: "Classic wood", light: "#f0d9b5", dark: "#b58863" },
  { value: "tournament_green", label: "Tournament green", light: "#ebecd0", dark: "#779556" },
  { value: "midnight_blue", label: "Midnight blue", light: "#dee3eb", dark: "#3e6ae1" },
  { value: "slate", label: "Slate", light: "#e8eaed", dark: "#5c5e62" },
  { value: "high_contrast", label: "High contrast", light: "#ffffff", dark: "#282828" },
];

const TERMINAL = new Set(["completed", "failed", "cancelled"]);
type WorkspaceTab = "create" | "preview" | "history";

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return minutes ? `${minutes}:${String(remaining).padStart(2, "0")}` : `${remaining}s`;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function presetLabel(value: string | null | undefined): string {
  return PRESETS.find((preset) => preset.value === value)?.label ?? value ?? "—";
}

function themeLabel(value: string | null | undefined): string {
  return BOARD_THEMES.find((theme) => theme.value === value)?.label ?? value ?? "Classic wood";
}

function gameTitle(job: ChessVideoJob): string {
  if (job.title) return job.title;
  if (job.white_player && job.black_player) return `${job.white_player} vs ${job.black_player}`;
  return `Job ${job.id.slice(0, 8)}`;
}

function statusLabel(status: string): string {
  if (status === "completed") return "Completed";
  if (status === "failed") return "Failed";
  if (status === "queued") return "Queued";
  if (status === "cancelled") return "Cancelled";
  return "Generating";
}

function JobStatusBadge({ status }: { status: string }) {
  const label = statusLabel(status);
  return (
    <span className="inline-flex min-h-7 items-center rounded-full border border-border bg-muted/40 px-2.5 text-xs font-medium capitalize text-muted-foreground">
      {label}
    </span>
  );
}

function GenerationStatus({
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

export default function ChessVideoPage() {
  const { tenantId, enabled } = useTenantScope();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("create");
  const [inputMode, setInputMode] = useState<"paste" | "upload">("paste");
  const [sourceText, setSourceText] = useState("");
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const [inputFormat, setInputFormat] = useState<ChessInputFormat>("auto");
  const [renderPreset, setRenderPreset] = useState<ChessRenderPreset>("economy_vertical");
  const [boardTheme, setBoardTheme] = useState<ChessBoardTheme>("classic_wood");
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
        board_theme: boardTheme,
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

  useEffect(() => {
    if (activeJob?.status === "completed" && activeJob.video_public_url) {
      setActiveTab("preview");
    }
  }, [activeJob?.status, activeJob?.video_public_url]);

  async function onUploadFile(file: File | null) {
    if (!file) return;
    const text = await file.text();
    setSourceText(text);
    setUploadedFileName(file.name);
    setInputFormat("pgn");
    setValidation(null);
    setInputMode("upload");
  }

  function removeUploadedFile() {
    setSourceText("");
    setUploadedFileName(null);
    setValidation(null);
    setUploadInputKey((key) => key + 1);
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 p-4 sm:p-6">
      <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <Swords className="size-5 text-primary" />
            <h1 className="text-2xl font-normal text-foreground">Chess Video</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            Turn a chess game into a shareable match video.
          </p>
        </div>
        {activeJob ? <JobStatusBadge status={activeJob.status} /> : null}
      </div>

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as WorkspaceTab)}>
        <TabsList className="w-full overflow-x-auto">
          <TabsTrigger value="create">Create</TabsTrigger>
          <TabsTrigger value="preview">
            Preview &amp; Export
            {activeJob?.video_public_url ? <span aria-hidden="true">●</span> : null}
          </TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="create" className="mt-5">
          <CreateVideoTab
            inputMode={inputMode}
            setInputMode={setInputMode}
            sourceText={sourceText}
            setSourceText={(value) => {
              setSourceText(value);
              setValidation(null);
              if (inputMode === "paste") {
                setUploadedFileName(null);
              }
            }}
            uploadedFileName={uploadedFileName}
            uploadInputKey={uploadInputKey}
            onUploadFile={onUploadFile}
            onRemoveUploadedFile={removeUploadedFile}
            inputFormat={inputFormat}
            setInputFormat={setInputFormat}
            renderPreset={renderPreset}
            setRenderPreset={setRenderPreset}
            orientation={orientation}
            setOrientation={setOrientation}
            secondsPerMove={secondsPerMove}
            setSecondsPerMove={setSecondsPerMove}
            boardTheme={boardTheme}
            setBoardTheme={setBoardTheme}
            includeCoordinates={includeCoordinates}
            setIncludeCoordinates={setIncludeCoordinates}
            includeMoveText={includeMoveText}
            setIncludeMoveText={setIncludeMoveText}
            title={title}
            setTitle={setTitle}
            validation={validation}
            validatePending={validateMutation.isPending}
            validateError={validateMutation.error}
            createPending={createMutation.isPending}
            createError={createMutation.error}
            canGenerate={canGenerate}
            activeJob={activeJob}
            retrying={retryMutation.isPending}
            onValidate={() => validateMutation.mutate()}
            onGenerate={() => createMutation.mutate()}
            onRetry={() => activeJob && retryMutation.mutate(activeJob.id)}
            onViewVideo={() => setActiveTab("preview")}
          />
        </TabsContent>

        <TabsContent value="preview" className="mt-5">
          <PreviewVideoTab
            activeJob={activeJob}
            onEditSettings={() => setActiveTab("create")}
            onRegenerate={() => {
              setActiveTab("create");
              if (canGenerate) {
                createMutation.mutate();
              }
            }}
            regenerating={createMutation.isPending}
            onRetry={() => activeJob && retryMutation.mutate(activeJob.id)}
            retrying={retryMutation.isPending}
          />
        </TabsContent>

        <TabsContent value="history" className="mt-5">
          <VideoHistoryTab
            jobs={recentJobs}
            loading={jobsQuery.isPending}
            error={jobsQuery.isError}
            deleteError={deleteMutation.error}
            deletingJobId={deleteMutation.isPending ? deleteMutation.variables : undefined}
            onRetryLoad={() => void jobsQuery.refetch()}
            onPreview={(jobId) => {
              setActiveJobId(jobId);
              setActiveTab("preview");
            }}
            onDelete={(jobId) => {
              if (!window.confirm("Delete this chess video job? This cannot be undone.")) {
                return;
              }
              deleteMutation.mutate(jobId);
            }}
            onCreate={() => setActiveTab("create")}
          />
        </TabsContent>
      </Tabs>

      <Button asChild variant="ghost" size="sm" className="self-start">
        <Link to="/dashboard">Back to dashboard</Link>
      </Button>
    </div>
  );
}

function CreateVideoTab({
  inputMode,
  setInputMode,
  sourceText,
  setSourceText,
  uploadedFileName,
  uploadInputKey,
  onUploadFile,
  onRemoveUploadedFile,
  inputFormat,
  setInputFormat,
  renderPreset,
  setRenderPreset,
  orientation,
  setOrientation,
  secondsPerMove,
  setSecondsPerMove,
  boardTheme,
  setBoardTheme,
  includeCoordinates,
  setIncludeCoordinates,
  includeMoveText,
  setIncludeMoveText,
  title,
  setTitle,
  validation,
  validatePending,
  validateError,
  createPending,
  createError,
  canGenerate,
  activeJob,
  retrying,
  onValidate,
  onGenerate,
  onRetry,
  onViewVideo,
}: {
  inputMode: "paste" | "upload";
  setInputMode: (value: "paste" | "upload") => void;
  sourceText: string;
  setSourceText: (value: string) => void;
  uploadedFileName: string | null;
  uploadInputKey: number;
  onUploadFile: (file: File | null) => void;
  onRemoveUploadedFile: () => void;
  inputFormat: ChessInputFormat;
  setInputFormat: (value: ChessInputFormat) => void;
  renderPreset: ChessRenderPreset;
  setRenderPreset: (value: ChessRenderPreset) => void;
  orientation: "white" | "black";
  setOrientation: (value: "white" | "black") => void;
  secondsPerMove: number;
  setSecondsPerMove: (value: number) => void;
  boardTheme: ChessBoardTheme;
  setBoardTheme: (value: ChessBoardTheme) => void;
  includeCoordinates: boolean;
  setIncludeCoordinates: (value: boolean) => void;
  includeMoveText: boolean;
  setIncludeMoveText: (value: boolean) => void;
  title: string;
  setTitle: (value: string) => void;
  validation: ChessVideoValidation | null;
  validatePending: boolean;
  validateError: unknown;
  createPending: boolean;
  createError: unknown;
  canGenerate: boolean;
  activeJob: ChessVideoJob | undefined;
  retrying: boolean;
  onValidate: () => void;
  onGenerate: () => void;
  onRetry: () => void;
  onViewVideo: () => void;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Card className="space-y-6 p-4 sm:p-6">
        <section className="space-y-3">
          <SectionHeader title="Game source" description="Paste moves or upload a PGN to validate the game." />
          <GameSourceInput
            inputMode={inputMode}
            setInputMode={setInputMode}
            sourceText={sourceText}
            setSourceText={setSourceText}
            uploadedFileName={uploadedFileName}
            uploadInputKey={uploadInputKey}
            onUploadFile={onUploadFile}
            onRemoveUploadedFile={onRemoveUploadedFile}
          />
          <GameSummary validation={validation} validating={validatePending} />
          {validateError ? (
            <ErrorState
              message={
                validateError instanceof Error
                  ? validateError.message
                  : "Validation request failed. Check the moves and try again."
              }
              onRetry={onValidate}
            />
          ) : null}
        </section>

        <section className="space-y-4 border-t border-border pt-5">
          <SectionHeader title="Video settings" description="Choose the output format and playback rhythm." />
          <div className="grid gap-4 lg:grid-cols-4">
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Input format</span>
              <select
                className="h-11 w-full rounded-md border border-border bg-background px-3 py-2"
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
                className="h-11 w-full rounded-md border border-border bg-background px-3 py-2"
                value={renderPreset}
                onChange={(e) => setRenderPreset(e.target.value as ChessRenderPreset)}
              >
                {PRESETS.map((preset) => (
                  <option key={preset.value} value={preset.value}>
                    {preset.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Board orientation</span>
              <select
                className="h-11 w-full rounded-md border border-border bg-background px-3 py-2"
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
                className="h-11"
                type="number"
                min={0.2}
                max={10}
                step={0.1}
                value={secondsPerMove}
                onChange={(e) => setSecondsPerMove(Number(e.target.value) || 1)}
              />
            </label>
          </div>
        </section>

        <section className="space-y-4 border-t border-border pt-5">
          <SectionHeader title="Board appearance" description="Pick a board style for the rendered video." />
          <BoardThemeSelector boardTheme={boardTheme} setBoardTheme={setBoardTheme} />
        </section>

        <section className="grid gap-4 border-t border-border pt-5 md:grid-cols-[1fr_1.4fr]">
          <div className="space-y-3">
            <SectionHeader title="Display options" />
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeCoordinates}
                  onChange={(e) => setIncludeCoordinates(e.target.checked)}
                />
                Coordinates
              </label>
              <label className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeMoveText}
                  onChange={(e) => setIncludeMoveText(e.target.checked)}
                />
                Move notation
              </label>
            </div>
          </div>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Video title</span>
            <Input
              className="h-11"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Match title"
            />
          </label>
        </section>

        <div className="flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-end">
          {sourceText.trim() && !validation?.valid ? (
            <p className="text-sm text-muted-foreground sm:mr-auto">
              Validate the game before generating.
            </p>
          ) : null}
          <Button
            type="button"
            variant="secondary"
            disabled={!sourceText.trim() || validatePending}
            onClick={onValidate}
          >
            {validatePending ? "Validating..." : "Validate Game"}
          </Button>
          <Button
            type="button"
            variant="primary"
            disabled={!canGenerate || createPending}
            onClick={onGenerate}
          >
            <Play className="size-4" />
            {createPending ? "Queuing..." : "Generate Video"}
          </Button>
        </div>

        {createError ? (
          <ErrorState
            message={
              createError instanceof Error
                ? createError.message
                : "Could not queue chess video job. Try again after checking the source."
            }
            onRetry={onGenerate}
          />
        ) : null}
      </Card>

      <aside className="space-y-4">
        {activeJob ? (
          <GenerationStatus
            job={activeJob}
            onViewVideo={onViewVideo}
            onRetry={onRetry}
            retrying={retrying}
          />
        ) : (
          <div className="rounded-md border border-dashed border-border bg-muted/20 p-4 text-sm text-muted-foreground">
            Generation status will appear here after you queue a video.
          </div>
        )}
      </aside>
    </div>
  );
}

function SectionHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div>
      <h2 className="text-sm font-medium text-foreground">{title}</h2>
      {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
    </div>
  );
}

function GameSourceInput({
  inputMode,
  setInputMode,
  sourceText,
  setSourceText,
  uploadedFileName,
  uploadInputKey,
  onUploadFile,
  onRemoveUploadedFile,
}: {
  inputMode: "paste" | "upload";
  setInputMode: (value: "paste" | "upload") => void;
  sourceText: string;
  setSourceText: (value: string) => void;
  uploadedFileName: string | null;
  uploadInputKey: number;
  onUploadFile: (file: File | null) => void;
  onRemoveUploadedFile: () => void;
}) {
  return (
    <Tabs value={inputMode} onValueChange={(value) => setInputMode(value as "paste" | "upload")}>
      <TabsList>
        <TabsTrigger value="paste">Paste Moves</TabsTrigger>
        <TabsTrigger value="upload">Upload PGN</TabsTrigger>
      </TabsList>
      <TabsContent value="paste" className="mt-4">
        <Textarea
          className="min-h-[240px] resize-y font-mono text-sm"
          value={sourceText}
          onChange={(e) => setSourceText(e.target.value)}
          placeholder="Paste PGN, SAN, or UCI moves..."
        />
      </TabsContent>
      <TabsContent value="upload" className="mt-4 space-y-3">
        <label className="flex min-h-[160px] cursor-pointer flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-muted/20 p-5 text-center text-sm transition-colors hover:bg-muted/35">
          <Upload className="size-6 text-muted-foreground" />
          <span className="font-medium text-foreground">
            {uploadedFileName ? uploadedFileName : "Drop or choose a PGN file"}
          </span>
          <span className="text-muted-foreground">PGN or plain text files are supported.</span>
          <Input
            key={uploadInputKey}
            className="sr-only"
            type="file"
            accept=".pgn,.txt,text/plain"
            onChange={(e) => onUploadFile(e.target.files?.[0] ?? null)}
          />
        </label>
        {sourceText ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground">
                {uploadedFileName ? `Loaded ${uploadedFileName}` : "Loaded PGN text"}
              </p>
              <Button type="button" variant="ghost" size="sm" onClick={onRemoveUploadedFile}>
                <X className="size-4" />
                Remove
              </Button>
            </div>
            <Textarea rows={6} value={sourceText} readOnly className="font-mono text-xs" />
          </div>
        ) : null}
      </TabsContent>
    </Tabs>
  );
}

function GameSummary({
  validation,
  validating,
}: {
  validation: ChessVideoValidation | null;
  validating: boolean;
}) {
  if (validating) {
    return (
      <div className="rounded-md border border-border bg-muted/25 p-4 text-sm text-muted-foreground">
        Validating game...
      </div>
    );
  }

  if (!validation) return null;

  if (!validation.valid) {
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        {validation.errors[0] || "Invalid game. Review the move text and validate again."}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border bg-muted/25 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <CheckCircle2 className="size-4 text-primary" />
        Game detected
      </div>
      <div className="mt-3 grid gap-3 text-sm sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        <p className="font-medium">{validation.white_player || "White"}</p>
        <span className="text-muted-foreground">vs</span>
        <p className="font-medium">{validation.black_player || "Black"}</p>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">
        {validation.event || "Untitled game"}
        {" · "}
        {validation.move_count} moves
        {" · "}
        {(validation.detected_format || validation.input_format).toUpperCase()}
        {validation.result ? ` · Result ${validation.result}` : ""}
      </p>
    </div>
  );
}

function BoardThemeSelector({
  boardTheme,
  setBoardTheme,
}: {
  boardTheme: ChessBoardTheme;
  setBoardTheme: (value: ChessBoardTheme) => void;
}) {
  return (
    <fieldset>
      <legend className="sr-only">Board theme</legend>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {BOARD_THEMES.map((theme) => {
          const selected = boardTheme === theme.value;
          return (
            <button
              key={theme.value}
              type="button"
              aria-pressed={selected}
              onClick={() => setBoardTheme(theme.value)}
              className={`min-h-16 rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                selected
                  ? "border-primary bg-primary/5 text-foreground ring-1 ring-primary/30"
                  : "border-border bg-background text-muted-foreground hover:border-foreground/30 hover:text-foreground"
              }`}
            >
              <span className="flex items-center gap-2">
                <span className="grid size-8 shrink-0 grid-cols-2 grid-rows-2 overflow-hidden rounded-sm border border-border">
                  <span style={{ background: theme.light }} />
                  <span style={{ background: theme.dark }} />
                  <span style={{ background: theme.dark }} />
                  <span style={{ background: theme.light }} />
                </span>
                <span className="min-w-0 flex-1 font-medium">{theme.label}</span>
                {selected ? <CheckCircle2 className="size-4 shrink-0 text-primary" /> : null}
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function PreviewVideoTab({
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

function VideoDetails({ job }: { job: ChessVideoJob }) {
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

function VideoHistoryTab({
  jobs,
  loading,
  error,
  deleteError,
  deletingJobId,
  onRetryLoad,
  onPreview,
  onDelete,
  onCreate,
}: {
  jobs: ChessVideoJob[];
  loading: boolean;
  error: boolean;
  deleteError: unknown;
  deletingJobId?: string;
  onRetryLoad: () => void;
  onPreview: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  onCreate: () => void;
}) {
  return (
    <Card className="p-4 sm:p-6">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-medium text-foreground">Recent videos</h2>
          <p className="text-sm text-muted-foreground">Review previous renders and reopen completed videos.</p>
        </div>
        <Button type="button" variant="secondary" size="sm" onClick={onCreate}>
          Create new
        </Button>
      </div>

      {loading ? <LoadingState label="Loading chess videos" /> : null}
      {error ? (
        <ErrorState message="Could not load chess video jobs." onRetry={onRetryLoad} />
      ) : null}

      {!loading && !error && jobs.length === 0 ? (
        <div className="rounded-md border border-dashed border-border p-6 text-center">
          <p className="font-medium text-foreground">No generated videos yet.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create your first chess video to see it here.
          </p>
        </div>
      ) : null}

      {jobs.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="border-b border-border text-xs font-medium text-muted-foreground">
              <tr>
                <th className="py-2 pr-4">Game</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Moves</th>
                <th className="py-2 pr-4">Created</th>
                <th className="py-2 pr-4">Duration</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td className="max-w-[260px] py-3 pr-4">
                    <button
                      type="button"
                      className="block truncate text-left font-medium text-foreground hover:underline"
                      onClick={() => onPreview(job.id)}
                    >
                      {gameTitle(job)}
                    </button>
                    <p className="truncate text-xs text-muted-foreground">{job.event || job.id}</p>
                  </td>
                  <td className="py-3 pr-4">
                    <JobStatusBadge status={job.status} />
                  </td>
                  <td className="py-3 pr-4 text-muted-foreground">{job.move_count}</td>
                  <td className="py-3 pr-4 text-muted-foreground">{formatDate(job.created_at)}</td>
                  <td className="py-3 pr-4 text-muted-foreground">{formatDuration(job.duration_seconds)}</td>
                  <td className="py-3">
                    <div className="flex justify-end gap-1">
                      <Button type="button" variant="ghost" size="sm" onClick={() => onPreview(job.id)}>
                        {job.video_public_url ? "Preview" : "View"}
                      </Button>
                      {job.video_public_url ? (
                        <Button asChild variant="ghost" size="sm">
                          <a href={job.video_public_url} download>
                            <Download className="size-4" />
                          </a>
                        </Button>
                      ) : null}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground hover:text-destructive"
                        aria-label={`Delete chess video job ${job.id.slice(0, 8)}`}
                        disabled={deletingJobId === job.id}
                        onClick={() => onDelete(job.id)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {deleteError ? (
        <div className="mt-4">
          <ErrorState
            message={
              deleteError instanceof Error
                ? deleteError.message
                : "Could not delete chess video job."
            }
          />
        </div>
      ) : null}
    </Card>
  );
}

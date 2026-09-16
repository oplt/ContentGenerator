import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Swords } from "lucide-react";
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
  type ChessVideoValidation,
} from "../api/chessVideos";
import {
  GamesWorkspace,
  PuzzlesWorkspace,
  type ChessWorkspaceTab,
} from "../features/chess";
import {
  CreateVideoTab,
  JobStatusBadge,
  PreviewVideoTab,
  TERMINAL_STATUSES,
  VideoHistoryTab,
} from "../features/chess/video";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { useTenantScope } from "../hooks/useTenantScope";
import { queryKeys } from "../lib/queryKeys";

export default function ChessVideoPage() {
  const { tenantId, enabled } = useTenantScope();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ChessWorkspaceTab>("create");
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
      if (!status || TERMINAL_STATUSES.has(status)) return false;
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
      if (activeJobId === jobId) setActiveJobId(null);
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
      // Completion is delivered by query polling, so tab state follows that external event.
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
            <h1 className="text-2xl font-normal text-foreground">Chess</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            Research historical games and puzzles, then analyze or render shareable match videos.
          </p>
        </div>
        {activeJob ? <JobStatusBadge status={activeJob.status} /> : null}
      </div>

      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as ChessWorkspaceTab)}>
        <TabsList className="w-full overflow-x-auto">
          <TabsTrigger value="games">Games</TabsTrigger>
          <TabsTrigger value="puzzles">Puzzles</TabsTrigger>
          <TabsTrigger value="create">Create</TabsTrigger>
          <TabsTrigger value="preview">
            Preview
            {activeJob?.video_public_url ? <span aria-hidden="true">●</span> : null}
          </TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="games" className="mt-5">
          <GamesWorkspace
            onUseInCreator={(game) => {
              setSourceText(game.normalized_pgn);
              setInputFormat("pgn");
              setInputMode("paste");
              setUploadedFileName(null);
              setValidation(null);
              if (game.famous_title) setTitle(game.famous_title);
              setActiveTab("create");
            }}
            onVideoJobCreated={(jobId) => {
              setActiveJobId(jobId);
              setActiveTab("preview");
            }}
          />
        </TabsContent>

        <TabsContent value="puzzles" className="mt-5">
          <PuzzlesWorkspace />
        </TabsContent>

        <TabsContent value="create" className="mt-5">
          <CreateVideoTab
            inputMode={inputMode}
            setInputMode={setInputMode}
            sourceText={sourceText}
            setSourceText={(value) => {
              setSourceText(value);
              setValidation(null);
              if (inputMode === "paste") setUploadedFileName(null);
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
              if (canGenerate) createMutation.mutate();
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
              if (!window.confirm("Delete this chess video job? This cannot be undone.")) return;
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
